# 03 — Screen map

## 1. Mobile app (React Native + Expo)

```mermaid
flowchart TD
    Launch[Launch / splash] --> LocPerm{Location permission}
    LocPerm -- granted --> Feed
    LocPerm -- denied --> ManualLoc[Manual city / neighborhood] --> Feed

    subgraph Discovery [Discovery - no login]
        Feed[Feed: list sorted by distance + next date]
        Feed <--> Map[Map view toggle]
        Feed --> Search[Search bar]
        Search --> Filters[Filters sheet: categories, price, radius, days and time, modality, language]
        Feed --> Detail[Experience detail]
        Map --> Detail
        Detail --> Gallery[Photos / videos]
        Detail --> ProviderPage[Provider page]
        Detail --> SpacePage[Space page]
        Detail --> Reviews[All reviews]
        Detail --> AskQ[Ask a question - needs login]
    end

    Feed --> Plus[+ menu]
    Plus --> CreateExp
    Plus --> ManageExp
    Plus --> Profile

    subgraph Checkout [Booking]
        Detail -- Book a session --> PickSession[Select session / course cohort]
        PickSession --> Seats[Number of seats]
        Seats --> AuthGate{Logged in?}
        AuthGate -- no --> Signup
        AuthGate -- yes --> Review
        Review[Review: listed price, service fee, total, policy, hold timer] --> Pay[Native payment sheet: card / Apple Pay / Google Pay]
        Pay --> Confirmed[Confirmed: address unlocked, add to calendar, message provider]
        Pay -- requires approval --> Pending[Pending provider approval]
    end

    subgraph Auth [Progressive signup / login]
        Signup[Phone or email] --> OTP[OTP code]
        Signup --> Apple[Sign in with Apple]
        Signup --> Google[Sign in with Google]
        OTP --> Complete[Complete profile: name, DOB 18+, phone verify, optional languages, optional accessibility + consent]
        Apple --> Complete
        Google --> Complete
        Complete --> Privacy[Privacy notice acceptance]
        Privacy --> Review
    end

    subgraph LearnerProfile [My profile]
        Profile[Profile home] --> Upcoming[Upcoming bookings]
        Upcoming --> BookingDetail[Booking detail: address, map, time, message, add to calendar]
        BookingDetail --> CancelQuote[Cancel: exact refund amount] --> CancelDone[Cancelled]
        Profile --> Past[Past classes - pending reviews highlighted]
        Past --> WriteReview[Write review]
        Profile --> Interests
        Profile --> Bio[Bio and languages]
        Profile --> Notif[Notification settings]
        Profile --> PayMethods[Saved payment methods]
        Profile --> Conduct[My conduct score] --> Appeal[Appeal]
        Profile --> PrivacyCenter[Privacy: consents, data export, delete account]
        Profile --> Inbox
    end

    subgraph Messaging
        Inbox[Inbox] --> Thread[Thread] --> Report[Report]
    end

    subgraph ProviderTools [Provider]
        CreateExp[Create experience wizard] --> Onboard{Provider + KYC?}
        Onboard -- no --> BecomeProvider[Become provider] --> KYC[Payment onboarding / KYC - gateway hosted]
        Onboard -- yes --> Wizard
        KYC --> Wizard
        Wizard[1 Basics: title, category, language, modality, type<br/>2 Content: what you'll learn, who it's for<br/>3 Price and seats<br/>4 Schedule: sessions / cohort / recurrence<br/>5 Location: space + map pin, or online link<br/>6 Media<br/>7 About me / about my space<br/>8 Publication window, policy, approval threshold] --> SaveDraft[Save draft] --> Submit[Submit for review]
        ManageExp[My experiences by status] --> EditExp[Edit - material edits re-review]
        ManageExp --> Sessions[Sessions] --> Roster[Roster + conduct scores + attendance]
        Roster --> RateLearner[Rate learner]
        ManageExp --> Approvals[Pending approvals]
        ManageExp --> Earnings[Earnings and payouts]
        ManageExp --> Inbox
    end
```

### Navigation shell

Per the brief, the first screen is the feed and the only global entry is the top-right "+" menu. Proposed: **no bottom tab bar** in MVP, with Inbox and Bookings reachable from "My profile". Open decision O-UX1: a 3-tab bar (Explore, Bookings, Inbox) usually raises retention for booking apps; I'd recommend it, your call.

### Screen count (MVP, Phases 1–3)

| Area | Screens |
|---|---|
| Discovery | 7 |
| Auth / signup | 5 |
| Checkout | 5 |
| Learner profile | 12 |
| Messaging | 3 |
| Provider | ~14 (wizard counted as 1 with 8 steps) |
| **Total** | **~46** |

## 2. Admin (extended Django admin, web)

```mermaid
flowchart LR
    Dash[Dashboard: queues + counters] --> RQ[Experience review queue]
    RQ --> RQD[Revision diff vs live: approve / request changes / reject + reason code]
    Dash --> PV[Provider verification: KYC status, ID, proof of address, space photos]
    Dash --> FQ[Flag queue: experiences, reviews, messages, users]
    Dash --> RD[Refunds and disputes: manual refund with override reason, chargeback evidence]
    Dash --> CA[Conduct appeals]
    Dash --> CFG[Config: fee bps, cancellation policies + rules, categories]
    Dash --> AL[Audit log - read only]
    Dash --> US[Users: suspend, anonymize, data export]
```

Every write action in admin goes through a service function that records an `AdminAction`, so the audit log can't be bypassed by editing a model form directly.
