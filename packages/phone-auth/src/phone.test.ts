import { describe, expect, it } from 'vitest';
import { COUNTRIES, formatIndianMobile, maskPhone, nationalDigits, toE164 } from './countries';
import { toPhoneAuthError } from './click-otp';

describe('phone helpers', () => {
  it('validates national numbers per country and builds E.164', () => {
    const IN = COUNTRIES[0]!;
    expect(IN.pattern.test('9876543210')).toBe(true);
    expect(IN.pattern.test('1234567890')).toBe(false);
    expect(toE164(IN, '98765 43210')).toBe('+919876543210');
  });

  it('accepts Indian mobile numbers only, however they are typed', () => {
    expect(COUNTRIES.map((c) => c.iso)).toEqual(['IN']);
    expect(nationalDigits('+91 98765 43210')).toBe('9876543210');
    expect(nationalDigits('098765 43210')).toBe('9876543210');
    expect(nationalDigits('919876543210')).toBe('9876543210');
    expect(formatIndianMobile('9876543210')).toBe('98765 43210');
  });

  it('masks phone numbers for display', () => {
    expect(maskPhone('+919876543210')).toBe('+91 9876••••10');
  });

  it('maps Click OTP error codes to friendly messages, never raw codes', () => {
    expect(toPhoneAuthError({ code: 'invalid_code' }).message).toBe('That code isn’t correct. Please try again.');
    expect(toPhoneAuthError({ code: 'otp_cooldown' }).code).toBe('too_many_requests');
    expect(toPhoneAuthError({ code: 'code_expired' }).code).toBe('code_expired');
    expect(toPhoneAuthError({ code: 'something_new' }).message).not.toContain('something_new');
  });
});
