# learnspace (working name)

Two-sided marketplace for learning experiences in Mexico City: independent instructors, studios and schools publish classes, workshops and courses; learners discover them nearby, book and attend.

| Phase | Status | Docs |
|---|---|---|
| 0 — Design | Done | [docs/phase-0](docs/phase-0/00-README.md) |
| 1 — Auth, discovery, provider creation, admin review | Done | [docs/phase-1](docs/phase-1/README.md) |
| 2 — Booking, payments (Stripe Connect), cancellations, notifications, learner profile | **Done, awaiting approval** | [docs/phase-2](docs/phase-2/README.md) |
| 3 — Reviews, conduct scores, messaging, online experiences | Not started | |

Deploying: [docs/deploy.md](docs/deploy.md). What runs in test mode and how to switch it to real: [docs/going-live.md](docs/going-live.md).

## Repository layout

```
backend/   Django 5.2 + DRF modular monolith, PostgreSQL 16 + PostGIS 3.4
  apps/accounts     users, OTP/Apple/Google auth, 18+ gate, consent, providers, ID verification
  apps/catalog      categories, areas, spaces, experiences, revisions, sessions, media, feed
  apps/booking      seat holds, bookings, cancellations, attendance, calendar files
  apps/payments     fee, PaymentProvider (Stripe Connect + fake), refunds, transfers, withholding, webhooks
  apps/notifications push (Expo) + email, preferences, reminders
  apps/moderation   admin review queue, reason codes, append-only audit log, reports
  apps/reviews, messaging   empty until Phase 3
mobile/    React Native + Expo SDK 57 (TypeScript, expo-router)
docs/      phase deliverables, ERD, API outline, decisions
```

## Backend: local setup

Option A, Docker (Postgres + API + worker):

```bash
docker compose up --build
docker compose exec api python manage.py seed_cdmx     # 200 experiences + test accounts
```

Option B, native (what CI-style runs use):

```bash
# PostgreSQL 16 with PostGIS 3 and GDAL installed locally
createuser -s learnspace && createdb -O learnspace learnspace
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # edit as needed; export the variables (or use direnv)
export DEBUG=1
python manage.py migrate && python manage.py createcachetable
python manage.py seed_cdmx
python manage.py runserver 0.0.0.0:8000
python manage.py procrastinate worker      # background jobs (media processing, emails), separate shell
```

Test accounts created by `seed_cdmx`:

| Role | Login | Notes |
|---|---|---|
| Admin | `admin@seed.learnspace.local` / `learnspace-dev-2026` | http://localhost:8000/admin/ |
| Learner | phone `55 0000 0001` | OTP code is printed in the server log (`sms.console`) |
| Provider | phone `55 0000 0002` | ID-verified, payouts and RFC set |

Payments in development use `PAYMENT_GATEWAY=fake` (default): checkout shows a test-mode payment and the API simulates Stripe's webhook, so the full booking → refund → payout cycle works without Stripe keys. Admin 2FA is optional in development and enforced elsewhere (`manage.py enable_admin_2fa <email>`).

Checks:

```bash
cd backend && . .venv/bin/activate
pytest                      # 186 tests (needs the PostGIS database above)
ruff check .
python manage.py bench_feed # feed latency through the full Django stack
```

## Mobile: local setup

```bash
cd mobile
npm install
EXPO_PUBLIC_API_URL=http://<your-LAN-IP>:8000/api/v1 npx expo start
```

- Feed, detail, filters, OTP login and the provider wizard run in **Expo Go**.
- **Sign in with Apple / Google** and native maps with a Google key need a development build (`npx expo run:ios|android` or `eas build --profile development`) plus client IDs in `app.json > extra` (see `GOOGLE_*` and `APPLE_CLIENT_IDS` in `backend/.env.example`).
- On a physical device, `localhost` is the phone; use your computer's LAN IP and add it to `ALLOWED_HOSTS`.
- `npx expo start --web` gives a browser preview (maps show a placeholder; DEV only). Set `DEV_CORS_ORIGINS=http://localhost:8081` on the backend for it.

Checks:

```bash
npm run typecheck && npx eslint src && npm test
```

## Configuration

Every deploy-specific value is an environment variable; see [`backend/.env.example`](backend/.env.example). Secrets never live in the repo. Brand and legal entity are placeholders (`BRAND_NAME`, `LEGAL_ENTITY_NAME`, `LEGAL_RFC`) until the operating entity is final.
