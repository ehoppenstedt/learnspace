import { router } from 'expo-router';
import { Alert } from 'react-native';

import i18n from './i18n';
import { ApiError, api } from './api/client';
import type { Thread } from './api/types';

async function open(body: Record<string, string>) {
  try {
    const thread = await api<Thread>('/threads', { method: 'POST', body });
    router.push(`/inbox/${thread.id}`);
  } catch (err) {
    Alert.alert(err instanceof ApiError ? err.message : i18n.t('errors.network'));
  }
}

/** Learner → host, from an experience or booking (one thread per learner and experience). */
export const openThreadForBooking = (experienceId: string) => open({ experience_id: experienceId });

/** Host → learner; only possible once the learner has booked. */
export const openThreadAsProvider = (bookingId: string) => open({ booking_id: bookingId });
