import { initPaymentSheet, initStripe, presentPaymentSheet } from '@stripe/stripe-react-native';
import Constants from 'expo-constants';

import type { PaymentSheetParams } from '../api/types';

export type PayResult = { outcome: 'paid' } | { outcome: 'cancelled' } | { outcome: 'error'; message: string };

/** Native Stripe PaymentSheet: cards, Apple Pay and Google Pay in one sheet; 3-D Secure handled by Stripe. */
export async function collectPayment(sheet: PaymentSheetParams, merchantName: string): Promise<PayResult> {
  await initStripe({
    publishableKey: sheet.publishable_key,
    merchantIdentifier: Constants.expoConfig?.extra?.stripeMerchantIdentifier as string | undefined,
    urlScheme: 'learnspace',
  });
  const customer = sheet.customer_ephemeral_key
    ? { customerId: sheet.customer_id, customerEphemeralKeySecret: sheet.customer_ephemeral_key }
    : {};
  const init = await initPaymentSheet({
    merchantDisplayName: merchantName,
    paymentIntentClientSecret: sheet.payment_intent_client_secret,
    ...customer,
    applePay: { merchantCountryCode: 'MX' },
    googlePay: { merchantCountryCode: 'MX', testEnv: __DEV__ },
    returnURL: 'learnspace://stripe-redirect',
    allowsDelayedPaymentMethods: false,
  } as Parameters<typeof initPaymentSheet>[0]);
  if (init.error) return { outcome: 'error', message: init.error.message };
  const result = await presentPaymentSheet();
  if (result.error) return result.error.code === 'Canceled' ? { outcome: 'cancelled' } : { outcome: 'error', message: result.error.message };
  return { outcome: 'paid' };
}

export const supportsRealPayments = true;
