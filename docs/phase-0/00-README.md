# Phase 0 — Discovery and design

Status: **approved** (2026-10-06). Defaults accepted for every "Blocks Phase 1" question; Stripe Connect chosen; fee set to 5%. Applied decisions are listed in [Phase 1](../phase-1/README.md#1-your-phase-0-answers-as-applied).

| Doc | Contents |
|---|---|
| [00-README.md](00-README.md) | This file: summary, clarifying questions, assumptions, compliance flags, open decisions |
| [01-erd.md](01-erd.md) | Data model (ERD in Mermaid), design decisions, feed indexes |
| [02-api-outline.md](02-api-outline.md) | REST endpoints, conventions, `PaymentProvider` interface, background jobs |
| [03-screen-map.md](03-screen-map.md) | Mobile screen map, admin screen map |
| [04-payments-comparison.md](04-payments-comparison.md) | Stripe Connect vs Mercado Pago vs Conekta, unit economics, recommendation |
| [05-dependencies.md](05-dependencies.md) | Every third-party service and package, with justification |

## 1. Clarifying questions

Grouped by the phase they block. **Phase 1 cannot start without the "Blocks Phase 1" answers.** Where I have a default, it's in brackets. Answering "default" is fine.

### Blocks Phase 1

| ID | Question | Why it matters | [Default] |
|---|---|---|---|
| Q-B0 | **Brand name, app name, and domain?** | Bundle IDs (`com.<brand>.app`), deep links, email sender domain, repo naming. Changing bundle IDs after store submission is painful. | Placeholder `learnspace` until you decide |
| Q-L1 | **Which legal entity operates the app?** The same entity as Gradiente (one RFC) or a new one? | Merchant of record, payment account, store accounts, privacy notice "responsable". Sharing an RFC partially defeats "fully separate". | New entity, or at minimum separate gateway/store accounts |
| Q-A1 | **Age gate depth.** Self-declared DOB only, or ID verification for learners too? | Self-declared is easy to bypass; ID checks add cost and friction. | Self-declared DOB for learners; ID check for providers |
| Q-A2 | **Phone OTP channel: SMS, WhatsApp, or both?** | WhatsApp is usually cheaper and has better delivery in MX; needs a Meta Business account. | SMS first, WhatsApp later |
| Q-A3 | **Can a learner book seats for other people, including minors?** "Number of seats" implies yes. Kids' art/music classes are a large segment. | If minors attend, the 18+ rule applies only to the account holder, and we need attendee names and a guardian waiver. Conduct rating applies only to the booker. | Yes, extra seats for adults only; no minors in MVP |
| Q-B1 | **Courses: one purchase for all sessions?** Can learners join a course after it started? Pro-rated price? | Drives `Cohort` model and inventory locking. | Whole course, one price; no joining after session 1 |
| Q-B2 | **Drop-in: single session only, or packs/passes (e.g., 4-class pack)?** | Packs add a credit ledger. | Single session only in MVP |
| Q-C1 | **Initial category list.** Confirm or edit: Art, Music, Theater & Performance, Comedy, Beauty & Makeup, Mechanics & Trades, Languages, Technology, Sports & Movement, Spirituality & Wellbeing, Cooking, Crafts, Business, Photography & Video, Dance. Flat or two levels? | Seed data and filters. | Flat list above |
| Q-I1 | **Hosting vendor and budget ceiling per month?** Any existing cloud account (not Gradiente's)? | Managed Postgres must support PostGIS. | Render or Fly.io, ~USD 50–100/month at launch |
| Q-M2 | **Media limits.** Max photos per experience, max video length/size? | Transcoding cost and storage. | 10 photos, 3 videos ≤ 60 s, ≤ 100 MB upload |

### Blocks Phase 2 (money)

| ID | Question | Why it matters | [Default] |
|---|---|---|---|
| Q-P1 | **Payment provider choice** (doc 04). | Everything in Phase 2. | Stripe Connect |
| Q-M1 | **Service fee %**, and does the shown fee **include IVA**? | LFPC requires the total incl. taxes. Example economics in doc 04 use 15% incl. IVA. | 15% incl. IVA (placeholder) |
| Q-T1 | **Have you consulted a tax advisor on the digital-platform withholding regime** (LISR 113-A / LIVA 18-J) and on whether providers' listed prices are IVA-inclusive? | Can turn "provider receives 100%" into "100% minus legal withholding". Also determines whether providers without RFC are allowed. | Blocked: needs advisor input |
| Q-M3 | **Rounding.** Fee rounded to the centavo, or totals rounded to whole pesos (e.g., 575 not 574.88)? | Display and fee math tests. | Round fee half-up to the centavo; show centavos only if non-zero |
| Q-P2 | **When does the provider get paid?** Proposed: transfer released 48 h after session end, weekly payout. | Chargeback and no-show protection vs provider cash flow. | 48 h after session end, weekly payout |
| Q-P3 | **No-show:** provider marks absent → 0% refund. Should the learner be able to dispute within 48 h before money is released? | Abuse in both directions. | Yes, dispute goes to admin queue |
| Q-P4 | **Provider cancellation penalty:** flag only, or consequences (e.g., 3 flags in 90 days = auto-pause; monetary penalty)? | Policy + admin tooling. | Flag + auto-pause at 3 in 90 days; no money |
| Q-P5 | **"Require approval for learners below X":** charge immediately and refund if declined, or authorize and capture on approval (card auth expires in ~7 days)? How long does the provider have to decide? | Payment flow differs. | Authorize, capture on approval; provider has 24 h, auto-decline after |
| Q-P6 | **Meses sin intereses (MSI)?** Common in MX, costly (fees 5–18%). | Out of scope unless you want it. | Not in MVP |
| Q-P7 | **Chargebacks/disputes:** who absorbs the loss if the provider is already paid? | Platform is merchant of record under the recommended model. | Platform absorbs; recover from future transfers if fraud by provider |

### Blocks Phase 3

| ID | Question | Why it matters | [Default] |
|---|---|---|---|
| Q-R1 | **Course reviews:** one review at course end, or per session? | Review window logic. | One review, window opens at last session end |
| Q-R2 | **Conduct score shown to providers:** raw average, or only after N ratings? | New learners would be judged on 1 rating. | Shown after 3 ratings, else "New" |
| Q-R3 | **Online experiences:** which video tool? Provider pastes any link (Zoom/Meet), or we integrate one? | Integration adds a dependency. | Provider pastes link |
| Q-MS1 | **Chat:** text only, or images too? | Moderation and storage. | Text only |

## 2. Assumptions I made (correct any)

1. Prices are per seat. Course price is for the whole course.
2. Time zone for everything user-facing: `America/Mexico_City`.
3. Cancellation windows are measured from the **first** session start for courses.
4. A learner can't book their own experience. A provider can be a learner elsewhere with the same account.
5. Providers need verified KYC to **publish**, not to draft.
6. Admin is Spanish + English, internal staff only, with 2FA (TOTP via Django; no extra dependency needed beyond a small package or ~100 lines of our code, decided in Phase 1).
7. Guests' filters live in device storage; on login they merge into the profile (profile wins on conflict).
8. Reviews can't be edited after submission; admin can hide them (moderation), not rewrite them.
9. "Seats remaining" is shown exactly when ≤ 5, otherwise "Available".
10. Learner accessibility needs are visible to the provider only for confirmed bookings, only for that session's roster, and never in admin lists (admin access to that field is logged).

## 3. Compliance flags

| Area | Flag |
|---|---|
| **Apple App Store** | In-person classes are "services consumed outside the app" (guideline 3.1.3(e)) → external payment allowed. Live online **one-to-one** classes fall under 3.1.3(d) (person-to-person) → external payment allowed. Live online **one-to-few / one-to-many** → Apple requires In-App Purchase. Plan: online experiences ship behind a server-side flag, hidden on iOS until we decide (IAP for group online, or online = 1:1 only on iOS). |
| **Google Play** | Same issue exists on Android: Play's payments policy exempts physical services, but live online group classes may require Play Billing (or an alternative-billing program). I'll check the current policy in Phase 3 before enabling. |
| **Sign in with Apple** | Mandatory on iOS because Google Sign-In is offered (guideline 4.8). Already in scope. |
| **LFPDPPP** | Mexico replaced its data protection law in 2025 (new LFPDPPP; the supervising authority changed). Privacy notice text, ARCO rights, and sensitive-data consent wording **need review by Mexican counsel**. I'll implement the mechanics: versioned notice, per-purpose consent records, encrypted sensitive data, data export, deletion/anonymization. |
| **LFPC** | Total price (listed + fee, incl. taxes) shown on feed, detail and checkout. Breakdown at checkout. |
| **Brand separation** | Separate repo (this one), separate DB, separate gateway account, separate store accounts, separate email domain. No shared code with Gradiente. |

## 4. Open decisions for you

1. Payment provider (doc 04) — **recommendation: Stripe Connect**.
2. Tax regime handling (Q-T1) — needs an advisor; blocks finalizing the money flow.
3. Navigation: "+" menu only, or add a 3-tab bar (O-UX1, doc 03) — **recommendation: tab bar**.
4. Hosting vendor (Q-I1).
5. Map geocoder: Google (best MX address coverage, needs billing account) vs Mapbox.
6. Chat transport: polling in MVP, websockets later if needed — **recommendation: polling**.
7. iOS strategy for online group classes (IAP vs 1:1 only vs hide on iOS).

## 5. Phase 1 plan (preview, after approval)

Repo layout: `backend/` (Django modular monolith: `accounts`, `catalog`, `booking`, `payments`, `reviews`, `messaging`, `moderation`, plus `core`), `mobile/` (Expo, TypeScript), `docs/`. Docker Compose for local Postgres+PostGIS. Phase 1 delivers: auth with 18+ gate, feed with geo filters and map, experience detail, provider creation wizard, admin review queue, CDMX seed data (~200 experiences across 15 categories and ~30 neighborhoods), tests, README.
