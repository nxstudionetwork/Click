import type { PhoneVerification } from '@click/phone-auth';

/**
 * The in-progress phone verification (number + provider handle). Memory only: it can't be
 * serialised and should not outlive the tab. After a reload the partner requests a new code.
 */
export interface PendingVerification {
  phone: string;
  verification: PhoneVerification;
  sentAt: number;
}

let pending: PendingVerification | null = null;

export const phoneFlow = {
  get: () => pending,
  start(phone: string, verification: PhoneVerification) {
    pending = { phone, verification, sentAt: Date.now() };
  },
  clear() {
    pending = null;
  },
};
