/**
 * In-progress sign-in state shared by the Login → Verify → Profile → Card screens.
 * The pending OTP verification lives in memory only. The signup token (signed by the
 * backend, valid 20 min) is kept in sessionStorage so a refresh during profile setup
 * doesn't force a new OTP; it is cleared as soon as signup completes.
 */
import type { PhoneVerification } from './phone';

let pending: PhoneVerification | null = null;
const KEY = 'click.signup';

export const onboarding = {
  setPending(v: PhoneVerification | null) { pending = v; },
  getPending: () => pending,
  saveSignup(token: string, phoneNumber: string) {
    try { sessionStorage.setItem(KEY, JSON.stringify({ token, phoneNumber, at: Date.now() })); } catch { /* storage unavailable */ }
  },
  getSignup(): { token: string; phoneNumber: string } | null {
    try {
      const v = JSON.parse(sessionStorage.getItem(KEY) ?? 'null');
      return v && Date.now() - v.at < 19 * 60_000 ? v : null;
    } catch { return null; }
  },
  clear() { pending = null; try { sessionStorage.removeItem(KEY); } catch { /* ignore */ } },
};
