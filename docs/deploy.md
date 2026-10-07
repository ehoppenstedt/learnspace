# Deploy guide (staging / production)

Target: Railway, hard usage limit USD 45/month. Everything is configured with environment variables; nothing secret is in the repo.

## 1. Accounts to create (under the operating entity, not Gradiente)

| Service | What for | Notes |
|---|---|---|
| Railway | API, worker, PostGIS | Set **Usage limit (hard) = USD 45** in workspace usage settings. |
| Stripe (Mexico) | Payments + Connect | Enable Connect; platform profile "marketplace"; Apple Pay merchant ID `merchant.com.learnspace.app`. |
| Cloudflare R2 | Media | Private bucket; create an S3 API token scoped to it. |
| Twilio | SMS OTP | Set a spending cap; buy/verify a sender for Mexico. |
| Amazon SES (or Postmark) | Email | Verify the sending domain (SPF/DKIM). |
| Expo (EAS) | Builds + push | `eas init` writes the project id; put it in `app.json > extra.eas.projectId`. |
| Sentry (optional) | Errors | Free tier. |

## 2. Railway services

1. **Database:** add a PostgreSQL service from a PostGIS image (`postgis/postgis:16-3.4`), or Railway's PostGIS template.
2. **api:** deploy this repo; `railway.toml` builds `backend/Dockerfile`, runs migrations and starts gunicorn on `$PORT`, health check `/healthz`.
3. **worker:** same repo and image, start command `python manage.py procrastinate worker` (runs jobs: media, refunds, transfers, reminders, notifications).

## 3. Environment variables (api and worker)

```
APP_ENV=production            # refuses to boot with dev defaults
SECRET_KEY=<random 50+ chars>
DATABASE_URL=postgis://...
ALLOWED_HOSTS=api.<domain>
PUBLIC_BASE_URL=https://api.<domain>
FIELD_ENCRYPTION_KEYS=k1:<base64 32 bytes>      # python -c "import os,base64;print('k1:'+base64.b64encode(os.urandom(32)).decode())"
LEGAL_ENTITY_NAME=...   LEGAL_RFC=...
PAYMENT_GATEWAY=stripe
STRIPE_SECRET_KEY=sk_live_...   STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRETS=whsec_platform,whsec_connect
MEDIA_STORAGE=s3  S3_BUCKET=...  S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com  S3_ACCESS_KEY_ID=...  S3_SECRET_ACCESS_KEY=...
SMS_BACKEND=apps.accounts.sms.TwilioSMSBackend  TWILIO_ACCOUNT_SID=...  TWILIO_AUTH_TOKEN=...  TWILIO_FROM_NUMBER=...
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend  EMAIL_HOST=email-smtp.<region>.amazonaws.com  EMAIL_HOST_USER=...  EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL="learnspace <no-reply@<domain>>"
PUSH_BACKEND=apps.notifications.push.ExpoPushBackend
APPLE_CLIENT_IDS=com.learnspace.app   GOOGLE_CLIENT_IDS=<ios>,<android>,<web client ids>
SENTRY_DSN=...
```

## 4. Stripe webhooks

Create two endpoints pointing to `https://api.<domain>/api/v1/webhooks/payments/stripe`:

- **Platform events:** `payment_intent.succeeded`, `payment_intent.amount_capturable_updated`, `payment_intent.payment_failed`, `payment_intent.canceled`, `refund.updated`, `refund.failed`, `charge.dispute.created`.
- **Connect events:** `account.updated`.

Put both signing secrets in `STRIPE_WEBHOOK_SECRETS`.

## 5. First run

```bash
railway run python manage.py createsuperuser
railway run python manage.py enable_admin_2fa you@<domain>              # scan the secret in your authenticator
railway run python manage.py enable_admin_2fa you@<domain> --code 123456
```

Admin: `https://api.<domain>/admin/`. Set the withholding rates (Payments → Withholding configs) as instructed by the tax advisor **before** the first payout.

## 6. Mobile builds

`app.json > extra`: `apiUrl`, `googleWebClientId`, `googleIosClientId`, `eas.projectId`, and Google Maps key for Android. Then `eas build --profile production` and `eas submit`.
