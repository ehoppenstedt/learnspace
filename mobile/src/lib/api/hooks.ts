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
  Booking,
  Earnings,
  NotificationPrefs,
  OnboardingStatus,
  ProviderBooking,
  RosterAttendee,
  SavedCard,
  ChatMessage,
  Credits,
  ExperienceReviews,
  MyConduct,
  PendingReviews,
  ProviderReview,
  Thread,
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

// ---------------------------------------------------------------- bookings (Phase 2)


export function useBookings(scope: 'upcoming' | 'past', enabled = true) {
  return useQuery({ queryKey: ['bookings', scope], queryFn: () => api<Booking[]>('/bookings', { query: { scope } }), enabled });
}

export function useBooking(id: string | undefined, poll = false) {
  return useQuery({
    queryKey: ['booking', id],
    queryFn: () => api<Booking>(`/bookings/${id}`),
    enabled: Boolean(id),
    // While a payment is settling, poll until the webhook has landed.
    refetchInterval: (q) => (poll && q.state.data?.status === 'pending_payment' ? 1500 : false),
  });
}

export function useRoster(sessionId: string | undefined) {
  return useQuery({
    queryKey: ['provider', 'roster', sessionId],
    queryFn: () => api<{ session: { id: string; starts_at: string; ends_at: string; capacity: number; seats_booked: number; status: string }; attendees: RosterAttendee[] }>(
      `/provider/sessions/${sessionId}/roster`),
    enabled: Boolean(sessionId),
  });
}

export function useProviderBookings(status?: string, enabled = true) {
  return useQuery({
    queryKey: ['provider', 'bookings', status],
    queryFn: () => api<ProviderBooking[]>('/provider/bookings', { query: { status } }),
    enabled,
  });
}

export function useOnboarding(enabled = true) {
  return useQuery({
    queryKey: ['provider', 'onboarding'],
    queryFn: () => api<OnboardingStatus>('/provider/payments/onboarding', { query: { refresh: 1 } }),
    enabled,
  });
}

export function useEarnings(enabled = true) {
  return useQuery({ queryKey: ['provider', 'earnings'], queryFn: () => api<Earnings>('/provider/earnings'), enabled });
}

export function useSavedCards(enabled = true) {
  return useQuery({ queryKey: ['me', 'cards'], queryFn: () => api<SavedCard[]>('/me/payment-methods'), enabled });
}

export function useNotificationPrefs(enabled = true) {
  return useQuery({ queryKey: ['me', 'prefs'], queryFn: () => api<NotificationPrefs>('/me/notification-prefs'), enabled });
}

// ---------------------------------------------------------------- reviews and messaging (Phase 3)

export function useExperienceReviews(id: string | undefined) {
  return useInfiniteQuery({
    queryKey: ['reviews', id],
    queryFn: ({ pageParam }) => api<ExperienceReviews>(`/experiences/${id}/reviews`, { query: { offset: pageParam } }),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
    enabled: Boolean(id),
  });
}

export function usePendingReviews(enabled = true) {
  return useQuery({ queryKey: ['me', 'pending-reviews'], queryFn: () => api<PendingReviews>('/me/reviews/pending'), enabled });
}

export function useMyConduct(enabled = true) {
  return useQuery({ queryKey: ['me', 'conduct'], queryFn: () => api<MyConduct>('/me/conduct'), enabled });
}

export function useProviderReviews(enabled = true) {
  return useQuery({ queryKey: ['provider', 'reviews'], queryFn: () => api<ProviderReview[]>('/provider/reviews'), enabled });
}

export function useThreads(enabled = true) {
  return useQuery({ queryKey: ['threads'], queryFn: () => api<Thread[]>('/threads'), enabled, refetchInterval: 30_000 });
}

export function useUnreadCount(enabled = true) {
  return useQuery({
    queryKey: ['threads', 'unread'],
    queryFn: () => api<{ unread: number }>('/threads/unread'),
    enabled,
    refetchInterval: 60_000,
  });
}

/** Messages poll every 4 s while the thread is open (no websockets in the MVP). */
export function useThreadMessages(id: string | undefined) {
  return useQuery({
    queryKey: ['thread', id],
    queryFn: () => api<{ thread: Thread; messages: ChatMessage[] }>(`/threads/${id}/messages`),
    enabled: Boolean(id),
    refetchInterval: 4_000,
  });
}

export function useCredits(enabled = true) {
  return useQuery({ queryKey: ['me', 'credits'], queryFn: () => api<Credits>('/me/credits'), enabled });
}
