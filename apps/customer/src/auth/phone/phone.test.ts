import { describe, expect, it } from 'vitest';
import { COUNTRIES, maskPhone, toE164 } from './countries';
import { toPhoneAuthError } from './firebase';

describe('phone helpers', () => {
  it('validates national numbers per country and builds E.164', () => {
    const IN = COUNTRIES[0]!;
    expect(IN.pattern.test('9876543210')).toBe(true);
    expect(IN.pattern.test('1234567890')).toBe(false);
    expect(toE164(IN, '98765 43210')).toBe('+919876543210');
  });

  it('masks phone numbers for display', () => {
    expect(maskPhone('+919876543210')).toBe('+91 9876••••10');
    expect(maskPhone('+16505550101')).toBe('+1 6505••••01');
  });

  it('maps Firebase error codes to friendly messages, never raw codes', () => {
    expect(toPhoneAuthError({ code: 'auth/invalid-verification-code' }).message).toBe('That code isn’t correct. Please try again.');
    expect(toPhoneAuthError({ code: 'auth/too-many-requests' }).code).toBe('too_many_requests');
    expect(toPhoneAuthError({ code: 'auth/code-expired' }).code).toBe('code_expired');
    expect(toPhoneAuthError({ code: 'auth/something-new' }).message).not.toContain('auth/');
  });
});
