import type { ImagePickerAsset } from 'expo-image-picker';

import { api } from '../api/client';
import type { Media } from '../api/types';

type UploadResponse = { id: string; upload: { method: 'PUT'; url: string; headers: Record<string, string> } };
type Status = { id: string; kind: string; status: 'pending_upload' | 'processing' | 'ready' | 'rejected'; rejection_reason: string; preview: Media | null };

function guessType(asset: ImagePickerAsset): string {
  if (asset.mimeType) return asset.mimeType;
  if (asset.type === 'video') return 'video/mp4';
  const ext = asset.uri.split('.').pop()?.toLowerCase();
  return ext === 'png' ? 'image/png' : ext === 'heic' ? 'image/heic' : 'image/jpeg';
}

/** Presigned upload: ask the API for a URL, PUT the bytes straight to storage, then confirm. */
export async function uploadAsset(asset: ImagePickerAsset, kind: 'image' | 'video' | 'document'): Promise<Status> {
  const contentType = guessType(asset);
  const blob = await (await fetch(asset.uri)).blob();
  const { id, upload } = await api<UploadResponse>('/media/uploads', {
    method: 'POST',
    body: { kind, content_type: contentType, bytes: asset.fileSize ?? blob.size },
  });
  const put = await fetch(upload.url, { method: 'PUT', headers: upload.headers, body: blob });
  if (!put.ok) throw new Error(`Upload failed (${put.status})`);
  return api<Status>(`/media/${id}/complete`, { method: 'POST' });
}

export async function pollMedia(id: string, attempts = 30): Promise<Status> {
  for (let i = 0; i < attempts; i++) {
    const status = await api<Status>(`/media/${id}`);
    if (status.status === 'ready' || status.status === 'rejected') return status;
    await new Promise((r) => setTimeout(r, 1500));
  }
  return api<Status>(`/media/${id}`);
}
