import { endConnection, fetchProducts, finishTransaction, initConnection, requestPurchase, type Purchase } from 'expo-iap';

export type StorePurchase = { outcome: 'paid'; signedTransaction: string; finish: () => Promise<void> } | { outcome: 'cancelled' } | { outcome: 'error'; message: string };

/**
 * Buys one App Store consumable (a price point) for a booking. The booking id travels as the
 * appAccountToken, so Apple signs it into the transaction and the server can match it.
 * Call finish() only after the server has verified the transaction.
 */
export async function buyOnAppStore(productId: string, appAccountToken: string): Promise<StorePurchase> {
  try {
    await initConnection();
    const products = await fetchProducts({ skus: [productId], type: 'in-app' });
    if (!products?.length) return { outcome: 'error', message: 'product_not_found' };
    const result = await requestPurchase({ request: { apple: { sku: productId, appAccountToken } }, type: 'in-app' });
    const purchase: Purchase | null | undefined = Array.isArray(result) ? result[0] : result;
    if (!purchase?.purchaseToken) return { outcome: 'cancelled' };
    return {
      outcome: 'paid',
      signedTransaction: purchase.purchaseToken, // StoreKit 2 JWS on iOS
      finish: async () => {
        await finishTransaction({ purchase, isConsumable: true });
        await endConnection();
      },
    };
  } catch (err) {
    const code = (err as { code?: string }).code ?? '';
    if (code.includes('cancel')) return { outcome: 'cancelled' };
    return { outcome: 'error', message: (err as Error).message };
  }
}
