# 05 — Third-party dependencies and justification

Rule applied: use a dependency only when building it ourselves is unreasonable (security-critical, regulated, platform-mandated, or months of work). Each row says what we'd have to build otherwise.

## 1. External services (accounts, contracts, money)

| # | Service | Purpose | Why not build it | Candidates (recommended first) | Decision owner |
|---|---|---|---|---|---|
| S1 | Payment gateway | Charges, KYC, transfers, payouts, refunds | Regulated (PCI DSS, KYC/AML, banking). Impossible to build. | **Stripe Connect**, Mercado Pago | You (see doc 04) |
| S2 | Managed Postgres + PostGIS | Primary DB | Backups, PITR, failover are ops work with no product value. | Must support PostGIS. **Render**, **Fly.io**, AWS RDS, GCP Cloud SQL | You (Q-I1) |
| S3 | Container hosting | API + worker | Same. | Same vendor as S2 to keep latency and billing simple | You (Q-I1) |
| S4 | S3-compatible object storage + CDN | Photos, videos, exports | Durable storage and signed URLs. | **Cloudflare R2** (no egress fees, matters for video), AWS S3 | Me, unless you have a preference |
| S5 | SMS for phone OTP | Phone verification at signup/login | Requires carrier relationships. | Twilio Verify, MessageBird/Bird, AWS SNS. **WhatsApp OTP** is often cheaper and more reliable in MX (Q-A2) | You (cost) |
| S6 | Transactional email | Confirmations, OTP by email, receipts, exports | Deliverability (SPF/DKIM/reputation) is not buildable. | **Amazon SES** (cheapest), Postmark (best deliverability), Resend | Me, unless you have a preference |
| S7 | Push delivery | Push notifications | APNs and FCM are mandatory platform gateways anyway. | **Expo Push Service** (wraps APNs + FCM, free, one API). Fallback: direct APNs/FCM later | Me |
| S8 | Maps SDK + geocoding | Map view, address → point, pin placement | Map tiles and geocoding are not buildable. | Map: `react-native-maps` (Apple Maps on iOS, Google Maps on Android; no Mapbox account). Geocoding: **Google Geocoding/Places** (best MX address coverage), Mapbox | You (Google Cloud billing account needed) |
| S9 | Error tracking | Crash + exception reporting, mobile and backend | Symbolication of RN crashes and source maps is significant work. | **Sentry** (SaaS, free tier) or **GlitchTip** (self-hosted, Sentry-protocol compatible, fewer features) | Me |
| S10 | Apple Developer + Google Play accounts | Distribution, Sign in with Apple, Apple Pay merchant ID | Mandatory. | Must be under the new brand's legal entity, not Gradiente's | You |
| S11 | Expo EAS Build/Submit | Cloud builds for iOS/Android | Avoids maintaining macOS build machines. Optional: local builds also work. | EAS free tier initially | Me |
| S12 | Tax/CFDI PAC (later) | CFDI for fee invoices and withholding receipts | Only SAT-authorized PACs can stamp CFDI. | Facturapi, others | You, after tax advice (Q-T1) |

## 2. Backend libraries (Python)

Kept deliberately small. Django already gives us ORM, migrations, admin, i18n, GeoDjango (PostGIS), cache, sessions, password hashing, signing, CSRF.

| # | Package | Purpose | Why not build it |
|---|---|---|---|
| B1 | `Django` | Framework | Decided. |
| B2 | `djangorestframework` | API, serializers, throttling | Decided. Its built-in throttling covers rate limits with the DB cache backend, so no Redis. |
| B3 | `psycopg` (v3) | Postgres driver | Required. |
| B4 | `djangorestframework-simplejwt` | Access/refresh tokens with rotation and blacklist | Token rotation and revocation are security-sensitive; DRF's built-in tokens have no expiry. |
| B5 | `PyJWT[crypto]` | Verify Apple and Google ID tokens against their JWKS | Avoids `django-allauth` (large, web-session oriented). ~80 lines of our own code on top. |
| B6 | `cryptography` | AES-GCM field encryption for sensitive data | Never hand-roll crypto primitives. |
| B7 | `procrastinate` | Postgres-backed job queue with periodic tasks, retries, LISTEN/NOTIFY | Meets "Postgres queue, no Redis". Has Django integration and cron-style schedules (hold expiry, reminders, review reveal). Alternative: `django-tasks` DB backend (lighter, fewer scheduling features). |
| B8 | `stripe` | Gateway SDK | Signature verification and API versioning; only imported inside the Stripe adapter. |
| B9 | `boto3` (Phase 1: used directly; `django-storages` not needed) | S3-compatible uploads, presigned URLs | Request signing (SigV4) is not worth reimplementing. `django-storages` is a thin, widely used wrapper; can be dropped if we only need presigned URLs. |
| B10 | `Pillow` + `pillow-heif` | Image resize/compress; iPhone HEIC uploads | HEIC decoding is a must for iOS photos. |
| B11 | `ffmpeg` (system binary in worker image) | Video transcoding, duration/size limits, poster frame | Industry standard; invoked via subprocess, no Python wrapper. Managed alternative (Mux, Cloudflare Stream) only if volume justifies it. |
| B12 | `sentry-sdk` | Error tracking | Pairs with S9. |
| B13 | `phonenumbers` | E.164 normalization, Mexican number validation, contact-info detection in chat | Number formats and metadata are maintained data, not code. |
| B14 | `icalendar` | `.ics` generation | Small; RFC 5545 escaping and time zones are easy to get wrong. Could be replaced with ~60 lines if you prefer zero deps here. |
| B15 | `gunicorn` | WSGI server | Required for production. |
| ~~B16~~ | ~~`structlog`~~ | Structured JSON logs | **Dropped in Phase 1:** a 25-line stdlib JSON formatter does the job. |
| Dev | `pytest`, `pytest-django`, `factory-boy`, `ruff`, `mypy`/`django-stubs`, `time-machine` | Tests, lint, types, time travel for hold/window tests | Dev-only. |

Not used, deliberately: Celery, Redis, Django Channels, django-allauth, GraphQL, Elasticsearch (Postgres FTS + `pg_trgm` is enough for CDMX scale).

## 3. Mobile libraries (TypeScript, Expo)

| # | Package | Purpose | Why not build it |
|---|---|---|---|
| M1 | `expo` + Expo modules: `expo-location`, `expo-notifications`, `expo-image-picker`, `expo-av`/`expo-video`, `expo-localization`, `expo-secure-store`, `expo-calendar`, `expo-apple-authentication` | Native capabilities | Decided stack. |
| M2 | `@stripe/stripe-react-native` | PaymentSheet: cards, Apple Pay, Google Pay, 3DS | PCI scope reduction; required for wallets. |
| M3 | `@react-native-google-signin/google-signin` | Google Sign-In | Native SDK wrapper; Expo has no first-party module. |
| M4 | `react-native-maps` | Map view | See S8. |
| M5 | `@react-navigation/*` (or `expo-router`) | Navigation | Standard. Recommend `expo-router` (file-based, deep links for booking/notification links). |
| M6 | `@tanstack/react-query` | Server state, caching, retries | Reimplementing caching/invalidation is error-prone. |
| M7 | `i18next` + `react-i18next` | ES/EN strings, pluralization | Pluralization rules and interpolation. |
| M8 | `@sentry/react-native` | Crash reporting | Pairs with S9. |
| Dev | `jest`, `@testing-library/react-native`, `typescript`, `eslint` | Tests, lint | Dev-only. |

No global state library: React Query + React context is enough at this size.

## 4. Running total

External services required at launch: 9 (S1–S9), plus store accounts. Backend runtime packages: 16 (one optional). Mobile runtime packages beyond Expo: 7.

## 5. Phase 1 actuals

What was actually installed, beyond the plan above:

| Package | Why |
|---|---|
| `expo-image` | Disk/memory image cache, smooth transitions, `recyclingKey` for fast lists. The feed is photo-first, so this matters more than anywhere else. |
| `@react-native-async-storage/async-storage` | Guest filters, chosen neighborhood and UI language persist on the device (non-secret data; tokens stay in `expo-secure-store`). |
| `@react-native-community/datetimepicker` | Native date/time pickers for session scheduling and the filter time window. |
| `expo-crypto` | SHA-256 nonce for Sign in with Apple (replay protection). |
| `react-native-web`, `react-dom`, `@expo/metro-runtime` | **Development preview only** (browser rendering of the app for reviews/screenshots). Not part of the iOS/Android binaries. |
| `expo-video` | Installed for in-detail video playback; currently the detail shows video posters. Remove if video stays out of Phase 2. |

Not installed yet (arrive with the phase that needs them): `@stripe/stripe-react-native` and `stripe` (Phase 2), `expo-notifications` (Phase 2), `@sentry/react-native` (before the first TestFlight build).

## 6. Phase 2 additions

| Package | Why |
|---|---|
| `stripe` (Python) | Request signing, webhook signature verification, API versioning. Only imported by the Stripe adapter. |
| `@stripe/stripe-react-native` | PaymentSheet: cards, Apple Pay, Google Pay, 3-D Secure, saved cards. Required for wallets and PCI scope. |
| `expo-notifications`, `expo-device` | Push token registration and notification taps (deep links to bookings). |
| `expo-web-browser` | Opens Stripe-hosted provider onboarding (KYC) in an in-app browser. |

Built in-house instead of adding packages: TOTP for admin 2FA (RFC 6238, ~30 lines), `.ics` generation (RFC 5545, ~40 lines), Twilio and Expo push clients (plain HTTPS).

## 7. Phase 4 additions

| Package | Why |
|---|---|
| `expo-iap` | StoreKit 2 In-App Purchase for group online classes on iOS (Apple guideline 3.1.1). Requires a development build. |
| `@sentry/react-native` | Crash reporting for pilot builds; inactive without `EXPO_PUBLIC_SENTRY_DSN`. |

Built in-house: StoreKit 2 JWS verification (certificate chain to the pinned Apple root, ~60 lines with `cryptography` + `PyJWT`, both already installed), credit ledger.
