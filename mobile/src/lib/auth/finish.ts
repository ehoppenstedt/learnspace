import { router, type Href } from 'expo-router';

import type { Me } from '../api/types';

/** Where to go after a successful login step. Profile completion is required before booking/teaching. */
export function continueAfterLogin(user: Me, next?: string) {
  if (!user.phone_verified) {
    router.replace({ pathname: '/auth/phone', params: next ? { next } : {} });
    return;
  }
  if (!user.profile_complete) {
    router.replace({ pathname: '/auth/complete-profile', params: next ? { next } : {} });
    return;
  }
  finishAuth(next);
}

export function finishAuth(next?: string) {
  if (router.canDismiss()) router.dismissAll();
  // Experience pages are already underneath the modal; anything else is pushed.
  if (next && !next.startsWith('/experience/')) router.push(next as Href);
}
