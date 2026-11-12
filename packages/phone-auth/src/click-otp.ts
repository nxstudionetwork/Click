/**
 * Click phone OTP adapter. The Click backend generates the code, texts it through the configured SMS provider and
 * verifies it; the app only sends the phone number, then the challenge id + typed code. No third-party SDK, widget
 * or script is loaded.
 */
import { FRIENDLY, PhoneAuthError, type PhoneAuthErrorCode, type PhoneAuthProvider } from './types';

const BASE = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, '');

const CODES: Record<string, PhoneAuthErrorCode> = {
  invalid_phone: 'invalid_phone',
  invalid_code: 'invalid_code',
  code_expired: 'code_expired',
  too_many_attempts: 'too_many_requests',
  too_many_requests: 'too_many_requests',
  otp_cooldown: 'too_many_requests',
  otp_unavailable: 'unavailable',
  otp_send_failed: 'unavailable',
  throttled: 'too_many_requests',
};

/** Maps a Click API error code (or a thrown value) to a customer-safe PhoneAuthError. */
export function toPhoneAuthError(err: unknown, message?: string): PhoneAuthError {
  if (err instanceof PhoneAuthError) return err;
  const raw = (err as { code?: string })?.code ?? '';
  const code = CODES[raw] ?? (typeof navigator !== 'undefined' && navigator.onLine === false ? 'network' : 'unknown');
  return new PhoneAuthError(code, raw === 'otp_cooldown' && message ? message : FRIENDLY[code], raw);
}

async function requestCode(phoneE164: string): Promise<{ challengeId: string; phoneNumber: string }> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/auth/otp/request`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ phone: phoneE164 }),
    });
  } catch {
    throw new PhoneAuthError('network', FRIENDLY.network);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw toPhoneAuthError(data?.error ?? { code: res.status === 429 ? 'too_many_requests' : 'unavailable' }, data?.error?.message);
  return data;
}

export const clickOtpAuth: PhoneAuthProvider = {
  id: 'phone_otp',
  async start(phoneE164) {
    const { challengeId, phoneNumber } = await requestCode(phoneE164);
    return {
      phoneNumber,
      // The backend checks the code during the identity exchange; nothing is verified in the browser.
      async confirm(code: string) {
        if (!/^\d{6}$/.test(code)) throw new PhoneAuthError('invalid_code', FRIENDLY.invalid_code);
        return { provider: 'phone_otp', token: `${challengeId}.${code}` };
      },
    };
  },
  async reset() { /* nothing held in the browser */ },
};
