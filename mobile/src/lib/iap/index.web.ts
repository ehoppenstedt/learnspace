export type StorePurchase = { outcome: 'paid'; signedTransaction: string; finish: () => Promise<void> } | { outcome: 'cancelled' } | { outcome: 'error'; message: string };

/** The App Store only exists on iOS; the web preview always uses test mode. */
export async function buyOnAppStore(): Promise<StorePurchase> {
  return { outcome: 'error', message: 'app_store_unavailable' };
}
