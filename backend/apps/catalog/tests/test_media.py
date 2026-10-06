import shutil
import subprocess
from io import BytesIO
from urllib.parse import urlparse

import pytest
from PIL import Image

from apps.catalog.models import MediaAsset
from apps.catalog.tasks import process_media_task
from conftest import auth

pytestmark = pytest.mark.django_db


def _jpeg_with_gps(size=(2000, 1500)) -> bytes:
    img = Image.new("RGB", size, (200, 80, 40))
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (19.0, 25.0, 9.0)}  # GPSInfo
    exif[0x0112] = 1
    out = BytesIO()
    img.save(out, "JPEG", exif=exif)
    return out.getvalue()


def _upload(api, kind, content_type, body: bytes):
    res = api.post("/api/v1/media/uploads", {"kind": kind, "content_type": content_type, "bytes": len(body)})
    assert res.status_code == 201, res.content
    url = urlparse(res.data["upload"]["url"])
    put = api.generic("PUT", f"{url.path}?{url.query}", body, content_type=content_type)
    assert put.status_code == 200
    return res.data["id"]


def test_image_pipeline_strips_metadata_and_makes_variants(api, learner, jobs, settings):
    auth(api, learner)
    asset_id = _upload(api, "image", "image/jpeg", _jpeg_with_gps())
    res = api.post(f"/api/v1/media/{asset_id}/complete")
    assert res.data["status"] == "processing"
    assert [j["task_name"] for j in jobs.jobs.values()] == ["apps.catalog.tasks.process_media_task"]

    process_media_task(asset_id=str(asset_id))
    asset = MediaAsset.objects.get(pk=asset_id)
    assert asset.status == "ready", asset.rejection_reason
    assert set(asset.variants) == {"w400", "w800", "w1600"}
    assert asset.dominant_color.startswith("#")
    variant = Image.open(settings.MEDIA_ROOT / asset.variants["w800"])
    assert variant.width == 800
    assert not variant.getexif().get(0x8825)  # GPS gone

    preview = api.get(f"/api/v1/media/{asset_id}").data["preview"]
    url = urlparse(preview["urls"]["w400"])
    assert api.get(f"{url.path}?{url.query}").status_code == 200


def test_signed_urls_are_required(api, learner):
    assert api.get("/media-local/get?t=forged").status_code == 403
    assert api.generic("PUT", "/media-local/put?t=forged", b"x").status_code == 403


def test_rejects_wrong_type_and_size(api, learner, settings):
    auth(api, learner)
    assert api.post("/api/v1/media/uploads", {"kind": "image", "content_type": "image/gif", "bytes": 10}).status_code == 400
    res = api.post("/api/v1/media/uploads", {"kind": "video", "content_type": "video/mp4",
                                             "bytes": settings.MEDIA_MAX_VIDEO_BYTES + 1})
    assert res.data["error"]["code"] == "file_too_large"


def test_tiny_image_rejected(api, learner):
    auth(api, learner)
    out = BytesIO()
    Image.new("RGB", (100, 100)).save(out, "PNG")
    asset_id = _upload(api, "image", "image/png", out.getvalue())
    api.post(f"/api/v1/media/{asset_id}/complete")
    process_media_task(asset_id=str(asset_id))
    asset = MediaAsset.objects.get(pk=asset_id)
    assert (asset.status, asset.rejection_reason) == ("rejected", "image_too_small")


def test_upload_must_exist_before_complete(api, learner):
    auth(api, learner)
    res = api.post("/api/v1/media/uploads", {"kind": "image", "content_type": "image/jpeg", "bytes": 100})
    assert api.post(f"/api/v1/media/{res.data['id']}/complete").status_code == 400


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
@pytest.mark.parametrize(("seconds", "max_seconds", "expected"), [(2, 60, "ready"), (3, 1, "rejected")])
def test_video_pipeline(api, learner, tmp_path, settings, seconds, max_seconds, expected):
    settings.MEDIA_MAX_VIDEO_SECONDS = max_seconds
    src = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=15:duration={seconds}",
                    "-pix_fmt", "yuv420p", str(src)], check=True)
    auth(api, learner)
    asset_id = _upload(api, "video", "video/mp4", src.read_bytes())
    api.post(f"/api/v1/media/{asset_id}/complete")
    process_media_task(asset_id=str(asset_id))
    asset = MediaAsset.objects.get(pk=asset_id)
    assert asset.status == expected
    if expected == "ready":
        assert {"mp4", "poster"} <= set(asset.variants)
        assert 1.5 < asset.duration_s < 2.5
    else:
        assert asset.rejection_reason == "video_too_long"
