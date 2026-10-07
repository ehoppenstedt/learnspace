# 02 — API outline

REST, JSON, versioned at `/api/v1`. Django REST Framework. The admin is Django admin (server-rendered) and does not use this API.

## Conventions

| Topic | Rule |
|---|---|
| Auth | Short-lived access token (15 min) + rotating refresh token (30 days). `Authorization: Bearer …`. |
| Language | `Accept-Language: es-MX` (default) or `en`. Catalog text is stored as the provider wrote it; UI strings and categories are translated. |
| Money | Integer centavos + `currency: "MXN"`. Every price object returns `{listed_cents, fee_cents, total_cents}`. Clients display `total_cents` only, except at checkout. |
| Time | ISO 8601 with offset. Server returns `America/Mexico_City` local fields too. |
| Pagination | Cursor (`?cursor=`), page size ≤ 50. |
| Idempotency | `Idempotency-Key` header **required** on `POST /bookings`, `POST /bookings/{id}/cancel`, refunds. Stored 24 h. |
| Errors | `{"error": {"code": "seat_unavailable", "message": "...", "fields": {...}}}`. Stable machine codes. |
| Rate limits | DRF throttles: OTP request 3/10 min per destination + 10/h per IP; OTP verify 5 attempts per challenge; login endpoints 20/h per IP. |
| Visibility | `G` guest, `L` learner, `P` provider, `A` admin, `S` server-to-server (webhooks). |

## accounts

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/auth/otp/request` | G | `{channel: sms\|email, destination}`. Always returns 202 (no account enumeration). |
| POST | `/auth/otp/verify` | G | `{challenge_id, code}` → tokens + `profile_complete: bool`. |
| POST | `/auth/apple` | G | `{identity_token, nonce}`. Server verifies against Apple JWKS. |
| POST | `/auth/google` | G | `{id_token}`. Server verifies against Google JWKS. |
| POST | `/auth/refresh` | L | Rotates refresh token; reuse of an old one revokes the family. |
| POST | `/auth/logout` | L | Revokes refresh token. |
| POST | `/me/complete-profile` | L | Progressive signup: first/last name, DOB (**rejects < 18**), phone (+ OTP if not yet verified), optional languages, optional accessibility needs **with explicit consent flag**. |
| GET / PATCH | `/me` | L | Profile, bio, UI language. |
| GET / PUT | `/me/filters` | L | Persisted feed filters. |
| GET / PUT | `/me/interests` | L | Category ids. |
| GET / PUT | `/me/notification-prefs` | L | |
| GET / POST / DELETE | `/me/consents` | L | Grant/revoke per purpose; revoking accessibility consent deletes that data. |
| POST | `/me/data-export` | L | Async job; emails a signed link (LFPDPPP access right). |
| DELETE | `/me` | L | Account deletion: blocked while there are upcoming confirmed bookings or unsettled payouts; otherwise anonymize. |
| POST / DELETE | `/me/devices` | L | Expo push token registration. |
| GET | `/me/conduct` | L | Own conduct score + revealed ratings. |
| POST | `/me/conduct/appeals` | L | |

## catalog

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/config` | G | Fee bps (for client display only, server is source of truth), categories, policies, supported languages, min app version. |
| GET | `/geo/resolve?q=` | G | Manual city/neighborhood → point (fallback when location is denied). Backed by a seeded CDMX neighborhood table first, geocoder second. |
| GET | `/experiences` | G | Feed. Params: `lat, lng` (or `area_id`), `radius_km` (default 10, max 50), `q`, `category[]`, `price_min/max` (on **total**), `dow[]`, `time_from`, `time_to`, `modality`, `language`, `sort=distance\|soonest`. Returns cards: title, cover, total price, distance (from public point), next session, seats left, rating. |
| GET | `/experiences/map` | G | `bbox=` → lightweight pins (id, public point, total price). Max 300 pins; clustered client-side. |
| GET | `/experiences/{id}` | G | Detail. Approximate area only. Exact address/online link included **only** if caller has a confirmed booking. |
| GET | `/experiences/{id}/sessions` | G | Upcoming sessions/cohorts with seats remaining. |
| GET | `/experiences/{id}/reviews` | G | Revealed public reviews + rating summary. |
| GET | `/providers/{id}` | G | Public provider page. |
| GET | `/spaces/{id}` | G | Public space page (P4: lists experiences running there). |

### Provider side

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/provider/activate` | L | Learner becomes provider (creates ProviderProfile). |
| GET | `/provider/onboarding` | P | KYC status + requirements. |
| POST | `/provider/onboarding/link` | P | Returns gateway-hosted onboarding URL (or embedded session). |
| POST | `/provider/verification-docs` | P | ID, proof of address, space photos (media ids). |
| GET / POST | `/provider/spaces` | P | |
| GET / POST | `/provider/experiences` | P | List (filter by status) / create draft. |
| GET / PATCH | `/provider/experiences/{id}` | P | Edit. Server classifies the change as material or not; material → new revision. |
| POST | `/provider/experiences/{id}/submit` | P | Draft → in_review. Blocked if KYC not verified (going live needs KYC; drafts don't). |
| POST | `/provider/experiences/{id}/pause` / `resume` | P | |
| GET / POST / PATCH / DELETE | `/provider/experiences/{id}/sessions` | P | Bulk create (recurring rule expanded server-side). Deleting a session with bookings = provider cancellation flow. |
| GET | `/provider/sessions/{id}/roster` | P | Learner first name, seats, conduct score, accessibility needs (only if consented). |
| POST | `/provider/sessions/{id}/attendance` | P | `[{booking_id, present\|absent}]`. Allowed from session start until +48 h. |
| POST | `/provider/bookings/{id}/approve` / `decline` | P | Only for experiences with the conduct threshold. |
| POST | `/provider/sessions/{id}/cancel` | P | Refunds 100% incl. fee to everyone, adds penalty. |
| GET | `/provider/earnings` | P | Transfers by status, withholdings, upcoming payout. |
| GET | `/provider/payouts` | P | |

## media

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/media/uploads` | L/P | `{kind, content_type, bytes}` → presigned PUT URL (5 min), size/type limits enforced in the signature. |
| POST | `/media/{id}/complete` | L/P | Enqueues compression/transcode. Status polled or pushed. |
| — | reads | G | Served through short-lived signed GET URLs (or a CDN with signed cookies). |

## booking

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/holds` | L | `{session_id \| cohort_id, seats}` → `{hold_id, expires_at, price: {listed, fee, total}}`. Row-lock, 10-min hold. 409 `seat_unavailable`. One active hold per user per session. |
| DELETE | `/holds/{id}` | L | Release early. |
| POST | `/bookings` | L | `{hold_id}` + `Idempotency-Key` → creates Booking(`pending_payment`) + gateway payment → `{booking_id, client_secret}` for the native payment sheet. |
| GET | `/bookings` | L | `?scope=upcoming\|past`. Past includes `review_pending`. |
| GET | `/bookings/{id}` | L | Address, map point, online link (if confirmed), times, provider contact via thread. |
| GET | `/bookings/{id}/calendar.ics` | L | Signed URL variant for calendar apps. |
| GET | `/bookings/{id}/cancellation-quote` | L | `{quote_id, rule_applied, refund: {listed, fee, total}, valid_until}`. Quote valid 2 min. |
| POST | `/bookings/{id}/cancel` | L | `{quote_id}` + `Idempotency-Key`. If the quote expired or the window changed, 409 and the client re-quotes. **The learner never gets a different amount than the one shown.** |

## payments

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/webhooks/payments/{gateway}` | S | Signature verified first; stored in `WebhookEvent` (unique `event_id`); processed in a job. 2xx returned after durable insert. |
| GET | `/me/payment-methods` | L | Saved cards (gateway customer). |
| DELETE | `/me/payment-methods/{id}` | L | |

Internal `PaymentProvider` interface (Python, not HTTP):

```python
class PaymentProvider(Protocol):
    def create_checkout(self, booking: Booking, customer: Customer) -> CheckoutSession: ...
    def capture(self, payment: Payment) -> PaymentResult: ...
    def refund(self, payment: Payment, listed_cents: int, fee_cents: int, reason: str) -> RefundResult: ...
    def onboard_provider(self, provider: ProviderProfile, return_url: str) -> OnboardingLink: ...
    def get_account_status(self, account: PaymentAccount) -> AccountStatus: ...
    def transfer(self, transfer: Transfer) -> TransferResult: ...
    def payout(self, payout: Payout) -> PayoutResult: ...           # no-op where gateway auto-pays out
    def verify_and_parse_webhook(self, headers: Mapping, body: bytes) -> GatewayEvent: ...
```

A `FakePaymentProvider` implements the same interface for tests and local dev.

## reviews

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/me/reviews/pending` | L/P | Bookings whose window is open and not yet reviewed by caller. |
| POST | `/bookings/{id}/review` | L | 1–5 × 4 (facilities only in-person) + public text + private note. Immutable once submitted. |
| POST | `/provider/bookings/{id}/conduct-rating` | P | 1–5 × 2 + admin-only note. |
| — | reveal | system | Job reveals both on second submission or at window close (14 days after session end). |

## messaging

| Method | Path | Who | Notes |
|---|---|---|---|
| GET / POST | `/threads` | L/P | Create pre-booking thread `{experience_id}` or open booking thread. |
| GET | `/threads/{id}/messages` | L/P | `?after=` for polling. |
| POST | `/threads/{id}/messages` | L/P | Server-side detection of phone/email/payment links when no confirmed booking exists → returns `warning`, client asks to confirm, resend with `acknowledged_warning: true`. |
| POST | `/reports` | L/P | `{target_type, target_id, reason_code, details}`. |

Transport: HTTP polling (active thread every 5 s, otherwise push notification). No websockets in MVP; avoids Django Channels + Redis. Revisit if chat volume justifies it (open decision).

## Background jobs (Postgres-backed queue)

| Job | Trigger |
|---|---|
| `expire_seat_holds` | every minute |
| `process_webhook_event` | on insert |
| `send_notification` | on event / scheduled (24 h, 2 h reminders) |
| `close_review_windows_and_reveal` | hourly |
| `release_transfers` | hourly (transfers whose `release_at` passed) |
| `refresh_experience_denorm` | on booking/session change |
| `expire_experiences` | daily (`publish_until`) |
| `process_media` | on upload complete |
| `data_export` | on request |
| `reconcile_payments` | nightly, compares gateway vs DB |

## Payment edge case worth stating now

3-D Secure can push a payment past the 10-minute hold. If a success webhook arrives for an expired hold: re-lock the session; if seats remain, confirm; otherwise auto-refund 100% (fee included) and notify. Tested explicitly in Phase 2.
