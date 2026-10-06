import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { feedQuery, type Filters, type Origin } from '../utils/filters';
import { api } from './client';
import type {
  AppConfig,
  Area,
  ExperienceDetail,
  FeedPage,
  MapPin,
  ProviderExperience,
  ProviderProfile,
  ProviderSession,
  ProviderSpace,
} from './types';

export function useConfig() {
  return useQuery({ queryKey: ['config'], queryFn: () => api<AppConfig>('/config', { auth: false }), staleTime: 10 * 60_000 });
}

export function useFeed(filters: Filters, origin: Origin | null, q: string, enabled = true) {
  const params = feedQuery(filters, origin, q);
  return useInfiniteQuery({
    queryKey: ['feed', params],
    queryFn: ({ pageParam }) => api<FeedPage>('/experiences', { query: { ...params, offset: pageParam } }),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
    enabled,
    staleTime: 60_000,
  });
}

export type Bbox = [number, number, number, number];

export function useMapPins(filters: Filters, q: string, bbox: Bbox | null) {
  const params = feedQuery(filters, null, q);
  delete (params as Record<string, unknown>).radius_km;
  const key = bbox?.map((n) => n.toFixed(3)).join(',');
  return useQuery({
    queryKey: ['map', params, key],
    queryFn: () => api<{ results: MapPin[] }>('/experiences/map', { query: { ...params, bbox: key } }),
    enabled: Boolean(bbox),
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });
}

export function useExperience(id: string | undefined) {
  return useQuery({
    queryKey: ['experience', id],
    queryFn: () => api<ExperienceDetail>(`/experiences/${id}`),
    enabled: Boolean(id),
  });
}

export function useAreas(q: string) {
  return useQuery({
    queryKey: ['areas', q],
    queryFn: () => api<Area[]>('/geo/areas', { query: { q }, auth: false }),
    staleTime: 60 * 60_000,
  });
}

// ---------------------------------------------------------------- provider

export function useProviderProfile(enabled: boolean) {
  return useQuery({ queryKey: ['provider', 'profile'], queryFn: () => api<ProviderProfile>('/provider/profile'), enabled });
}

export function useVerificationDocs(enabled: boolean) {
  return useQuery({
    queryKey: ['provider', 'docs'],
    queryFn: () => api<{ id: string; doc_type: string; status: string; reason_code: string }[]>('/provider/verification-docs'),
    enabled,
  });
}

export function useProviderExperiences(enabled: boolean) {
  return useQuery({
    queryKey: ['provider', 'experiences'],
    queryFn: () => api<ProviderExperience[]>('/provider/experiences'),
    enabled,
  });
}

export function useProviderExperience(id: string | undefined) {
  return useQuery({
    queryKey: ['provider', 'experience', id],
    queryFn: () => api<ProviderExperience>(`/provider/experiences/${id}`),
    enabled: Boolean(id && id !== 'new'),
  });
}

export function useProviderSessions(id: string | undefined) {
  return useQuery({
    queryKey: ['provider', 'sessions', id],
    queryFn: () => api<ProviderSession[]>(`/provider/experiences/${id}/sessions`),
    enabled: Boolean(id && id !== 'new'),
  });
}

export function useProviderSpaces(enabled: boolean) {
  return useQuery({ queryKey: ['provider', 'spaces'], queryFn: () => api<ProviderSpace[]>('/provider/spaces'), enabled });
}

export function useExperienceAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'submit' | 'pause' | 'resume' | 'discard-changes' }) =>
      api<ProviderExperience>(`/provider/experiences/${id}/${action}`, { method: 'POST' }),
    onSuccess: (data) => {
      qc.setQueryData(['provider', 'experience', data.id], data);
      qc.invalidateQueries({ queryKey: ['provider', 'experiences'] });
    },
  });
}
