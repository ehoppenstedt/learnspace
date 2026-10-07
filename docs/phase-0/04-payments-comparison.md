# 04 — Payment provider comparison and recommendation

Scope: Mexico, MXN, marketplace with platform fee on top, provider receives 100% of listed price, platform absorbs processing, cards + Apple Pay + Google Pay, React Native/Expo client.

> **Verification status.** Public pricing and docs were checked by web search on 2026-10-06. Direct fetches of stripe.com and some third-party pages were blocked from this environment, so figures marked † come from search snippets or secondary sources and **must be confirmed with each provider's sales team before signing**. Rates are before 16% IVA.

## 1. Comparison

| Criterion | Stripe Connect | Mercado Pago (Split Payments / marketplace) | Conekta |
|---|---|---|---|
| Marketplace split in MX | **Yes.** Mexico is a supported Connect platform country. Destination charges or separate charges & transfers; platform sets `application_fee` or transfers an exact amount. | **Yes.** Each seller links their MP account via OAuth; payment created with the seller's token and a `marketplace_fee`. | **Not publicly documented.** Standard product settles 100% to the merchant. A split would mean we collect everything and disperse to providers ourselves (regulatory and operational risk, see §3). |
| Provider payouts to bank | Automatic or manual schedule per connected account (daily/weekly/monthly), MXN to CLABE. | Funds land in the seller's **MP wallet**; seller withdraws to bank (free). We don't control the bank payout. | We'd have to build dispersion (SPEI) ourselves or via another provider. |
| KYC | Stripe-hosted or embedded onboarding; Stripe collects and verifies requirements (ID, RFC/CURP where required†, CLABE). Status via webhooks. | Done by MP when the seller opens their account. Lowest friction for sellers who already use MP. | Merchant KYC only; no sub-merchant KYC product we could find. |
| Who pays processing fee | Destination charges / SCT: **platform pays** Stripe's fee. Matches our model natively. | **MP fee is deducted from the seller's share**, then our `marketplace_fee` from the remainder. To give the provider 100% we must compute `marketplace_fee = total − listed − MP fee` per payment. Workable but brittle if MP changes fee tiers. | N/A (no split). |
| Refund control | Full: `refund_application_fee` + `reverse_transfer` with explicit amounts. With SCT, if the transfer hasn't been released yet, a refund only touches platform balance. "Full refund incl. fee" and "50% of listed, fee retained" are both exact. | **Refunds are split proportionally** between seller and marketplace. "Partial refund, fee retained" (whole refund from the provider's share) is **not** natively expressible; we'd need compensating transfers. Seller must have balance, otherwise the marketplace refunds only its share. | N/A. |
| Card fee (domestic) | 3.6% + MXN 3 † | 3.49% + MXN 4 (instant availability); 2.95% + MXN 4 at 30 days † | 3.4% + MXN 3 † |
| Marketplace-specific fees | Platform-managed pricing: MXN 35 per monthly active account + 0.25% + MXN 12 per payout † | No extra marketplace fee found. | — |
| Apple Pay / Google Pay | Supported in MX through the Payment Element / native PaymentSheet. | Not documented for online Checkout API in MX (Apple Pay in MX is MP's Tap to Pay for in-person merchants, a different product). Treat as **no** until MP confirms. | Listed as supported methods; iOS native component includes Apple Pay. Online checkout availability via API needs confirmation. |
| React Native SDK | **Official** `@stripe/stripe-react-native`, Expo config plugin, PaymentSheet with cards/Apple Pay/Google Pay, 3DS handled. | No official RN SDK. Options: Checkout Pro in a WebView/browser, or Card Bricks (web) in a WebView. Worse UX, more PCI surface to reason about. | No official RN SDK. Community `react-native-conekta` (unofficial). Official iOS component is native Swift only. |
| Webhooks | Signed (`Stripe-Signature`, HMAC + timestamp), event ids for dedupe, retries up to 3 days, event replay from dashboard, CLI for local testing. | Signed (`x-signature` HMAC) on current notification types; retries exist; historically less consistent across products (IPN vs webhooks). | Signed webhooks with retries; smaller ecosystem of tooling. |
| Local market fit | Neutral brand to learners. Supports MSI (installments) and OXXO if needed later. | **Strongest consumer trust in MX**; many learners already have MP balance. Big conversion advantage for wallet payers. | Mexican company, strong in OXXO/SPEI. |
| Lock-in / swap cost | Medium. Abstraction isolates it. | Medium-high: OAuth seller tokens are MP-specific. | — |

## 2. Unit economics example (one seat)

Assumptions: listed price MXN 500, service fee 15% (placeholder, see Q-M1), fee **includes** IVA.

| Line | Stripe | MP (instant) | MP (30-day) | Conekta |
|---|---|---|---|---|
| Learner pays | 575.00 | 575.00 | 575.00 | 575.00 |
| Processing (incl. IVA on fee) | 27.49 | 27.92 | 24.32 | 26.16 |
| Provider receives | 500.00 | 500.00 | 500.00 | 500.00 |
| Platform gross fee | 75.00 | 75.00 | 75.00 | 75.00 |
| − IVA on our fee (75/1.16) | −10.34 | −10.34 | −10.34 | −10.34 |
| − processing | −27.49 | −27.92 | −24.32 | −26.16 |
| **Platform net** | **37.17** | **36.74** | **40.34** | **38.50** |
| Net as % of listed | 7.4% | 7.3% | 8.1% | 7.7% |

Before Stripe's per-account and per-payout Connect fees (~MXN 35/active provider/month + ~MXN 12 + 0.25% per payout †). At small volume (e.g. a provider with 4 bookings/month) those add ~MXN 13 (one monthly payout) to ~MXN 22 (weekly payouts) per booking, which is material. Mitigation: weekly or monthly payouts, not daily.

Fee differences between providers are ±1 percentage point of listed price. **The bigger levers are the fee % itself and the tax treatment (Q-T1), not the gateway.**

## 3. Risks that apply regardless of provider

1. **Platform tax withholding (biggest open item).** Mexican law has a regime for digital platforms that intermediate services between third parties (LISR Art. 113-A and LIVA Art. 18-J, as I understand them). If it applies, the platform must withhold ISR and IVA from individual providers and report monthly to SAT, with much higher withholding when the provider has no RFC. That directly conflicts with "provider receives 100% of listed price" as a cash number. The model includes withholding columns on `Transfer`. **Needs a Mexican tax advisor before Phase 2.**
2. **CFDI.** Learners may request a CFDI for the service fee; providers may need CFDI de retenciones. Requires a PAC integration (not in MVP scope unless you say so).
3. **Holding funds.** Recommended flow releases provider money after the session ends. Gateways cap how long funds may be held before transfer (Stripe's limit depends on the country†). Courses spanning months need per-session releases.
4. **Merchant of record.** With destination charges / SCT the platform is the merchant of record and bears chargebacks. Budget for dispute losses; holding funds until after the class mitigates them.

## 4. Recommendation: Stripe Connect

**Integration pattern:** separate charges and transfers. Platform charges the learner the total; after the session ends + N days (proposed N = 2), a transfer of the listed amount (minus any legal withholding) goes to the provider's connected account; Stripe pays out to the provider's CLABE on a weekly schedule. Connected accounts configured with controller properties (Stripe's replacement for the old Express type, which is deprecated for new integrations), using Stripe-hosted onboarding for KYC.

Why:

1. **The fee model matches without workarounds.** Platform pays processing, provider gets an exact amount, and both refund rules (full incl. fee / 50% of listed, fee retained) are exact API calls. With MP, partial refunds are proportional by design, so the Standard policy needs compensating transfers.
2. **Apple Pay + Google Pay + official Expo-compatible SDK.** Required by the brief; only Stripe meets it with first-party support today.
3. **KYC and payouts are outsourced.** We don't build bank dispersion (Conekta) and we control payout timing (MP pays into a wallet we don't control).
4. **Webhook tooling** (signature, replay, CLI) reduces the risk on the most failure-prone part of the system.

What you give up:

- **~0.1–0.6 pp higher card cost than MP/Conekta**, plus Connect per-account/per-payout fees.
- **MP wallet trust and balance payments.** Mitigation: add Mercado Pago as a *payment method* later behind the same abstraction, settling to the platform (not as a split), if conversion data shows the need.
- **Stripe MX specifics to confirm with sales before Phase 2:** separate charges & transfers availability for an MX platform with MX connected accounts, maximum hold period, RFC requirements for individual providers, Apple Pay domain/merchant setup in MX, and Connect pricing.

**Second choice:** Mercado Pago, if the tax advisor concludes that providers must each be the merchant of record (MP's 1:1 model fits that better), or if Stripe can't onboard individual providers without RFC.

Conekta is not recommended for the marketplace use case because its public docs show no split/payout product.

## Sources

- [Stripe Connect (MX)](https://stripe.com/en-mx/connect) · [Connect pricing (MX)](https://stripe.com/en-mx/connect/pricing) · [Stripe pricing (MX)](https://stripe.com/en-mx/pricing) · [Express accounts (deprecation note, MX in platform list)](https://docs.stripe.com/connect/express-accounts) · [Migrate to controller properties](https://docs.stripe.com/connect/migrate-to-controller-properties) · [Connect risk and liability](https://docs.stripe.com/connect/risk-management) · [Stripe service provider in Mexico](https://support.stripe.com/questions/stripe-service-provider-in-mexico)
- [MP Split Payments prerequisites (MX)](https://www.mercadopago.com.mx/developers/en/docs/split-payments/split-1-1/prerequisites) · [MP marketplace integration (refund proportionality, fee order)](https://www.mercadopago.com.br/developers/en/docs/split-payments/integration-configuration/integrate-marketplace) · [MP Checkout API refunds (MX)](https://www.mercadopago.com.mx/developers/en/docs/checkout-api-payments/payment-management/cancellations-and-refunds/introduction) · [MP fees MX 2026 (secondary)](https://atempora.studio/blog/comisiones-mercado-pago-2026) · [Apple Tap to Pay in MX via MP (Bloomberg Línea)](https://www.bloomberglinea.com/latinoamerica/mexico/apple-habilita-cobros-con-iphone-en-mexico-a-traves-de-mercado-pago-clip-adyen-y-visa/)
- [Conekta pricing](https://www.conekta.com/pricing) · [Conekta cards](https://www.conekta.com/payments/cards) · [Conekta iOS components](https://github.com/conekta/conekta-components-ios) · [react-native-conekta (community)](https://github.com/zo0r/react-native-conekta)
