# Going live: what is in test mode today, and how to switch each piece

The app runs end to end without a Stripe account, tax rates or electronic invoicing. Each piece below is behind a switch, so turning on the real version is configuration (plus, for invoicing, one adapter), not a rewrite.

| Piece | Today (test mode) | What learners / providers see | To switch to real |
|---|---|---|---|
| **Payments** | `PAYMENT_GATEWAY=fake` | A "Pago de prueba" sheet with a fixed test card (no card data is ever typed), option to simulate a decline, and a "Modo de prueba" banner. Bookings, refunds, payouts and reminders all run the real logic. | Open Stripe (Mexico) with Connect, then set `PAYMENT_GATEWAY=stripe`, `STRIPE_*` keys and the two webhook secrets ([deploy.md](deploy.md)). The app switches to the real Stripe sheet (cards, Apple Pay, Google Pay) automatically. |
| **Provider payout account (KYC)** | Completes instantly with an explanation ("Verificación de prueba") | Checklist shows the step done | Same switch: providers are sent to Stripe's hosted identity and bank verification. |
| **Tax withholding (ISR/IVA)** | Rates are 0. Earnings show the withholding line at $0 with "Tasas de retención por definir". | Earnings: price, withholding ($0), deposit | Admin → Payments → Withholding configs → add a row with the rates from your tax advisor. Takes effect for new payouts; no deploy. |
| **Receipts / tax documents** | `RECEIPT_BACKEND=…DummyReceiptBackend`: printable HTML receipt per booking and a monthly statement per provider, clearly marked "no es un comprobante fiscal (CFDI)" | "Ver comprobante" on each booking; "Estado de cuenta del mes" on earnings | Contract a PAC (e.g. Facturapi), write a ~100-line adapter with the same two methods (`booking_receipt`, `provider_statement`) that returns the stamped CFDI, point `RECEIPT_BACKEND` to it. |
| **RFC** | Required, format-checked only | Providers enter their RFC; any valid-format RFC works (e.g. `XAXX010101000` for testing) | Admin marks "validated" after checking the SAT constancia. |

Safety rails:
- Test mode works on development and **staging** (for user testing with real people) but the server **refuses to start** in `APP_ENV=production` with the test gateway.
- Test-mode endpoints (simulated payment, simulated KYC) return 404 whenever a real gateway is configured.
- User-testing data created in test mode should not be migrated to production: start production with a clean database.
