import { describe, expect, it } from 'vitest';
import { formatMoney } from './format';

describe('formatMoney', () => {
  it('shows whole rupees without decimals and paise with exactly two', () => {
    expect(formatMoney('249.00')).toBe('₹249');
    expect(formatMoney('7.2')).toBe('₹7.20');
    expect(formatMoney(1486.05)).toBe('₹1,486.05');
  });
});
