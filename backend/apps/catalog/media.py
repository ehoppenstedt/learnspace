"""Upload lifecycle: request presigned URL -> client PUTs bytes -> complete -> background processing.

Images: EXIF-orientation applied, metadata stripped (removes GPS), resized to 400/800/1600 px
JPEG variants, dominant color computed for a placeholder while loading.
Videos: duration/size enforced, transcoded to <=720p H.264 MP4 with faststart, poster frame.
Documents (verification): stored as uploaded, never exposed outside admin.
"""

import json
import logging
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.utils.translation import gettext as _
from rest_framework import status

from apps.catalog.models import MediaAsset
from apps.catalog.storage import get_storage
from apps.core.exceptions import DomainError

logger = logging.getLogger(__name__)

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
VIDEO_TYPES = {"video/mp4", "video/quicktime"}
DOCUMENT_TYPES = IMAGE_TYPES | {"application/pdf"}
IMAGE_WIDTHS = (400, 800, 1600)

_ALLOWED = {
    MediaAsset.Kind.IMAGE: (IMAGE_TYPES, lambda: settings.MEDIA_MAX_IMAGE_BYTES),
    MediaAsset.Kind.VIDEO: (VIDEO_TYPES, lambda: settings.MEDIA_MAX_VIDEO_BYTES),
    MediaAsset.Kind.DOCUMENT: (DOCUMENT_TYPES, lambda: settings.MEDIA_MAX_IMAGE_BYTES),
}


def max_bytes_for(kind: str) -> int:
    return _ALLOWED[kind][1]()


def create_upload(user, *, kind: str, content_type: str, size: int) -> tuple[MediaAsset, dict]:
    if kind not in _ALLOWED:
        raise DomainError("invalid_media_kind", _("Tipo de archivo no permitido."), status.HTTP_400_BAD_REQUEST)
    types, max_bytes = _ALLOWED[kind][0], max_bytes_for(kind)
    if content_type not in types:
        raise DomainError("invalid_content_type", _("Formato no permitido."), status.HTTP_400_BAD_REQUEST)
    if size <= 0 or size > max_bytes:
        raise DomainError("file_too_large", _("El archivo excede el tamaño máximo."), status.HTTP_400_BAD_REQUEST,
                          fields={"max_bytes": max_bytes})
    asset = MediaAsset(owner=user, kind=kind, content_type=content_type, declared_bytes=size)
    asset.storage_key = f"{kind}/{user.pk}/{asset.id}/original"
    asset.save()
    return asset, get_storage().presigned_put(asset.storage_key, content_type, max_bytes)


def complete_upload(user, asset_id) -> MediaAsset:
    asset = MediaAsset.objects.filter(pk=asset_id, owner=user).first()
    if asset is None:
        raise DomainError("media_not_found", _("Archivo no encontrado."), status.HTTP_404_NOT_FOUND)
    if asset.status != MediaAsset.Status.PENDING_UPLOAD:
        return asset
    actual = get_storage().size(asset.storage_key)
    if actual is None:
        raise DomainError("upload_missing", _("No recibimos el archivo."), status.HTTP_400_BAD_REQUEST)
    if actual > max_bytes_for(asset.kind):
        asset.status, asset.rejection_reason = MediaAsset.Status.REJECTED, "file_too_large"
        asset.save(update_fields=["status", "rejection_reason", "updated_at"])
        return asset
    if asset.kind == MediaAsset.Kind.DOCUMENT:
        asset.status = MediaAsset.Status.READY
        asset.save(update_fields=["status", "updated_at"])
        return asset
    asset.status = MediaAsset.Status.PROCESSING
    asset.save(update_fields=["status", "updated_at"])
    from apps.catalog.tasks import process_media_task

    process_media_task.defer(asset_id=str(asset.pk))
    return asset


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------


def process(asset_id) -> MediaAsset:
    asset = MediaAsset.objects.get(pk=asset_id)
    if asset.status != MediaAsset.Status.PROCESSING:
        return asset
    try:
        if asset.kind == MediaAsset.Kind.IMAGE:
            _process_image(asset)
        elif asset.kind == MediaAsset.Kind.VIDEO:
            _process_video(asset)
    except _Rejected as exc:
        asset.status, asset.rejection_reason = MediaAsset.Status.REJECTED, str(exc)
        asset.save(update_fields=["status", "rejection_reason", "updated_at"])
        return asset
    asset.status = MediaAsset.Status.READY
    asset.save()
    return asset


class _Rejected(Exception):
    pass


def _process_image(asset: MediaAsset) -> None:
    import pillow_heif
    from PIL import Image, ImageOps, UnidentifiedImageError

    pillow_heif.register_heif_opener()
    storage = get_storage()
    try:
        img = Image.open(BytesIO(storage.read(asset.storage_key)))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise _Rejected("unreadable_image") from exc
    if min(img.size) < 400:
        raise _Rejected("image_too_small")
    asset.width, asset.height = img.size
    r, g, b = img.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    asset.dominant_color = f"#{r:02x}{g:02x}{b:02x}"
    base = asset.storage_key.rsplit("/", 1)[0]
    variants = {}
    for width in IMAGE_WIDTHS:
        copy = img.copy()
        if copy.width > width:
            copy = copy.resize((width, round(copy.height * width / copy.width)), Image.Resampling.LANCZOS)
        out = BytesIO()
        copy.save(out, "JPEG", quality=82, optimize=True, progressive=True)  # no EXIF: strips GPS
        key = f"{base}/w{width}.jpg"
        storage.write(key, out.getvalue(), "image/jpeg")
        variants[f"w{width}"] = key
    asset.variants = variants


def _process_video(asset: MediaAsset) -> None:
    if not shutil.which(settings.FFMPEG_BINARY) or not shutil.which(settings.FFPROBE_BINARY):
        logger.error("ffmpeg not available; cannot process video", extra={"asset_id": str(asset.pk)})
        raise _Rejected("processing_unavailable")
    storage = get_storage()
    base = asset.storage_key.rsplit("/", 1)[0]
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        src.write_bytes(storage.read(asset.storage_key))
        probe = subprocess.run(
            [settings.FFPROBE_BINARY, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
             "-of", "json", str(src)],
            capture_output=True, text=True, timeout=60,
        )
        if probe.returncode != 0:
            raise _Rejected("unreadable_video")
        info = json.loads(probe.stdout or "{}")
        duration = float(info.get("format", {}).get("duration") or 0)
        streams = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
        if not streams or duration <= 0:
            raise _Rejected("unreadable_video")
        if duration > settings.MEDIA_MAX_VIDEO_SECONDS + 0.5:
            raise _Rejected("video_too_long")
        out, poster = Path(tmp) / "out.mp4", Path(tmp) / "poster.jpg"
        transcode = subprocess.run(
            [settings.FFMPEG_BINARY, "-y", "-v", "error", "-i", str(src),
             "-vf", "scale='min(1280,iw)':-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
             "-map_metadata", "-1", str(out)],
            capture_output=True, text=True, timeout=600,
        )
        if transcode.returncode != 0:
            raise _Rejected("transcode_failed")
        subprocess.run(
            [settings.FFMPEG_BINARY, "-y", "-v", "error", "-ss", str(min(1.0, duration / 2)), "-i", str(src),
             "-frames:v", "1", "-vf", "scale=800:-2", str(poster)],
            capture_output=True, timeout=60, check=False,
        )
        storage.write(f"{base}/video.mp4", out.read_bytes(), "video/mp4")
        variants = {"mp4": f"{base}/video.mp4"}
        if poster.exists():
            storage.write(f"{base}/poster.jpg", poster.read_bytes(), "image/jpeg")
            variants["poster"] = f"{base}/poster.jpg"
    asset.duration_s = round(duration, 2)
    asset.width, asset.height = streams[0].get("width"), streams[0].get("height")
    asset.variants = variants


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _picsum(url: str, width: int) -> str:
    # Seed images use picsum "/seed/<slug>/<w>/<h>": rewrite size per variant.
    parts = url.rstrip("/").split("/")
    if "picsum.photos" in url and len(parts) >= 2 and parts[-1].isdigit() and parts[-2].isdigit():
        w, h = int(parts[-2]), int(parts[-1])
        return "/".join(parts[:-2] + [str(width), str(round(h * width / w))])
    return url


def public_media(asset: MediaAsset) -> dict | None:
    """Public representation. Never used for DOCUMENT assets."""
    if asset.kind == MediaAsset.Kind.DOCUMENT:
        return None
    payload = {
        "id": str(asset.pk),
        "kind": asset.kind,
        "width": asset.width,
        "height": asset.height,
        "color": asset.dominant_color or "#d9d9d9",
    }
    if asset.external_url:
        payload["urls"] = {f"w{w}": _picsum(asset.external_url, w) for w in IMAGE_WIDTHS}
        return payload
    if asset.status != MediaAsset.Status.READY:
        return None
    storage = get_storage()
    if asset.kind == MediaAsset.Kind.IMAGE:
        payload["urls"] = {name: storage.url(key) for name, key in asset.variants.items()}
    else:
        payload["video_url"] = storage.url(asset.variants["mp4"])
        payload["poster_url"] = storage.url(asset.variants["poster"]) if "poster" in asset.variants else None
        payload["duration_s"] = asset.duration_s
    return payload
