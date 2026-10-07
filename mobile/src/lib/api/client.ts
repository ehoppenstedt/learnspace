import { Platform } from 'react-native';

import { API_URL } from './config';
import { tokenStore } from '../auth/tokenStore';
import type { ApiErrorBody } from './types';

export class ApiError extends Error {
  status: number;
  code: string;
  fields: Record<string, unknown>;

  constructor(status: number, body: Partial<ApiErrorBody> | null) {
    super(body?.error?.message ?? `HTTP ${status}`);
    this.status = status;
    this.code = body?.error?.code ?? 'http_error';
    this.fields = body?.error?.fields ?? {};
  }

  /** First human-readable message for a field, if the server sent one. */
  fieldMessage(name: string): string | undefined {
    const value = this.fields[name];
    if (Array.isArray(value)) return String(value[0]);
    if (typeof value === 'string') return value;
    return undefined;
  }
}

type Options = {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  auth?: boolean;
};

let language = 'es';
export function setApiLanguage(lang: string) {
  language = lang;
}

let onSessionExpired: (() => void) | null = null;
export function setOnSessionExpired(cb: () => void) {
  onSessionExpired = cb;
}

export function buildUrl(path: string, query?: Options['query']): string {
  const url = `${API_URL}${path}`;
  if (!query) return url;
  const params = Object.entries(query)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&');
  return params ? `${url}?${params}` : url;
}

let refreshing: Promise<boolean> | null = null;

async function refreshTokens(): Promise<boolean> {
  const refresh = await tokenStore.getRefresh();
  if (!refresh) return false;
  const res = await fetch(buildUrl('/auth/refresh'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  });
  if (!res.ok) {
    await tokenStore.clear();
    return false;
  }
  const data = (await res.json()) as { access: string; refresh?: string };
  await tokenStore.set(data.access, data.refresh ?? refresh);
  return true;
}

export async function api<T>(path: string, opts: Options = {}, retried = false): Promise<T> {
  // The platform lets the server apply store rules (online experiences are off on iOS for now).
  const headers: Record<string, string> = { Accept: 'application/json', 'Accept-Language': language, 'X-Client-Platform': Platform.OS };
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
  // A keystore failure must never block public browsing: treat it as logged out.
  const access = opts.auth === false ? null : await tokenStore.getAccess().catch(() => null);
  if (access) headers.Authorization = `Bearer ${access}`;

  const res = await fetch(buildUrl(path, opts.query), {
    method: opts.method ?? 'GET',
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });

  if (res.status === 401 && access && !retried) {
    // Single-flight refresh so parallel requests don't rotate the token twice.
    refreshing = refreshing ?? refreshTokens().finally(() => (refreshing = null));
    if (await refreshing) return api<T>(path, opts, true);
    onSessionExpired?.();
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}
