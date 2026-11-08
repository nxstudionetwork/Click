import type { ConfirmationResult } from 'firebase/auth';

/**
 * The in-progress phone verification (number + Firebase confirmation handle).
 * Memory only: it can't be serialised and should not outlive the tab. If the
 * page reloads mid-verification the partner simply requests a new code.
 */
export interface PendingVerification {
  phone: string;
  confirmation: ConfirmationResult;
  sentAt: number;
}

let pending: PendingVerification | null = null;

export const phoneFlow = {
  get: () => pending,
  start(phone: string, confirmation: ConfirmationResult) {
    pending = { phone, confirmation, sentAt: Date.now() };
  },
  clear() {
    pending = null;
  },
};
