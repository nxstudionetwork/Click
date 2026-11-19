/** Supported dialling codes. `pattern` validates the national number (digits only) before any SMS is sent. */
export interface Country { iso: string; name: string; dial: string; flag: string; pattern: RegExp; example: string }

/** Click serves India: sign-in, verification and saved contacts use Indian mobile numbers only (+91, 10 digits, 6-9 first). */
export const INDIA: Country = { iso: 'IN', name: 'India', dial: '+91', flag: '🇮🇳', pattern: /^[6-9]\d{9}$/, example: '98765 43210' };
export const COUNTRIES: Country[] = [INDIA];

/** Whatever was typed or pasted -> the 10-digit national number (drops +91 / 91 / 0 prefixes, keeps at most 10 digits). */
export function nationalDigits(input: string): string {
  let d = input.replace(/\D/g, '');
  if (d.length > 10 && d.startsWith('91')) d = d.slice(2);
  else if (d.length > 10 && d.startsWith('0')) d = d.slice(1);
  return d.replace(/^0+/, '').slice(0, 10);
}

/** "9876543210" -> "98765 43210", formatted as the customer types. */
export const formatIndianMobile = (digits: string) => (digits.length > 5 ? `${digits.slice(0, 5)} ${digits.slice(5)}` : digits);

export const toE164 = (c: Country, national: string) => `${c.dial}${national.replace(/\D/g, '')}`;

/** "+919876543210" -> "+91 98765 •••10" for display. */
export function maskPhone(e164: string): string {
  const c = [...COUNTRIES].sort((a, b) => b.dial.length - a.dial.length).find((x) => e164.startsWith(x.dial));
  const nat = c ? e164.slice(c.dial.length) : e164;
  const masked = nat.length > 4 ? `${nat.slice(0, Math.max(2, nat.length - 6))}${'•'.repeat(Math.min(4, nat.length - 4))}${nat.slice(-2)}` : nat;
  return `${c?.dial ?? ''} ${masked}`.trim();
}
