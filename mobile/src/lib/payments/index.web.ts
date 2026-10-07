// Web preview (development) has no Stripe native SDK; only the fake gateway's test mode works.
import type { PaymentSheetParams } from '../api/types';

export type PayResult = { outcome: 'paid' } | { outcome: 'cancelled' } | { outcome: 'error'; message: string };

export async function collectPayment(_sheet: PaymentSheetParams, _merchantName: string): Promise<PayResult> {
  return { outcome: 'error', message: 'Card payments need the iOS/Android app.' };
}

export const supportsRealPayments = false;
