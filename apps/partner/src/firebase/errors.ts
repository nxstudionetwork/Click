/** Friendly, non-technical messages for Firebase phone-auth failures. Raw errors are never shown. */
const MESSAGES: Record<string, string> = {
  'auth/invalid-phone-number': 'That mobile number doesn’t look right. Check it and try again.',
  'auth/missing-phone-number': 'Enter your mobile number.',
  'auth/too-many-requests': 'Too many attempts. Please wait a few minutes and try again.',
  'auth/quota-exceeded': 'We couldn’t send a code right now. Please try again later.',
  'auth/invalid-verification-code': 'That code isn’t correct. Please try again.',
  'auth/missing-verification-code': 'Enter the 6-digit code.',
  'auth/code-expired': 'The verification code expired. Request a new one.',
  'auth/session-expired': 'The verification code expired. Request a new one.',
  'auth/invalid-verification-id': 'This verification session ended. Request a new code.',
  'auth/missing-verification-id': 'This verification session ended. Request a new code.',
  'auth/network-request-failed': 'You seem to be offline. Check your connection and try again.',
  'auth/captcha-check-failed': 'We couldn’t complete the security check. Please try again.',
  'auth/invalid-app-credential': 'We couldn’t complete the security check. Please try again.',
  'auth/missing-app-credential': 'We couldn’t complete the security check. Please try again.',
  'auth/user-disabled': 'This number has been disabled. Contact Click Partner support.',
  'auth/operation-not-allowed': 'Phone sign-in isn’t available right now. Please try again later.',
  'auth/internal-error': 'We couldn’t verify your number right now. Please try again.',
};

export const GENERIC_PHONE_ERROR = 'We couldn’t verify your number right now. Please try again.';

export function firebaseErrorCode(err: unknown): string {
  return typeof err === 'object' && err && 'code' in err && typeof err.code === 'string' ? err.code : '';
}

export function friendlyFirebaseError(err: unknown): string {
  return MESSAGES[firebaseErrorCode(err)] ?? GENERIC_PHONE_ERROR;
}

/** Errors after which the current code can't be used any more and a new one must be requested. */
export function needsNewCode(err: unknown): boolean {
  return ['auth/code-expired', 'auth/session-expired', 'auth/invalid-verification-id', 'auth/missing-verification-id']
    .includes(firebaseErrorCode(err));
}
