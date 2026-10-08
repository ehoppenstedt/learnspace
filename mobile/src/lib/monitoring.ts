import * as Sentry from '@sentry/react-native';

const dsn = process.env.EXPO_PUBLIC_SENTRY_DSN;

/** Crash and error reporting. Off unless EXPO_PUBLIC_SENTRY_DSN is set (e.g. in EAS build profiles). */
export function initMonitoring() {
  if (!dsn) return;
  Sentry.init({
    dsn,
    environment: process.env.EXPO_PUBLIC_APP_ENV ?? (__DEV__ ? 'development' : 'production'),
    sendDefaultPii: false, // no IPs or user data: the LFPDPPP notice doesn't cover sharing them with Sentry
    tracesSampleRate: 0.1,
  });
}

export const wrapRoot = (component: () => React.JSX.Element) => (dsn ? Sentry.wrap(component) : component);
