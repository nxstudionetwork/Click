/** Supported dialling codes. `pattern` validates the national number (digits only) before any SMS is sent. */
export interface Country { iso: string; name: string; dial: string; flag: string; pattern: RegExp; example: string }

export const COUNTRIES: Country[] = [
  { iso: 'IN', name: 'India', dial: '+91', flag: '🇮🇳', pattern: /^[6-9]\d{9}$/, example: '98765 43210' },
  { iso: 'US', name: 'United States', dial: '+1', flag: '🇺🇸', pattern: /^[2-9]\d{2}[2-9]\d{6}$/, example: '650 555 0101' },
  { iso: 'GB', name: 'United Kingdom', dial: '+44', flag: '🇬🇧', pattern: /^7\d{9}$/, example: '7400 123456' },
  { iso: 'AE', name: 'United Arab Emirates', dial: '+971', flag: '🇦🇪', pattern: /^5\d{8}$/, example: '50 123 4567' },
  { iso: 'SG', name: 'Singapore', dial: '+65', flag: '🇸🇬', pattern: /^[89]\d{7}$/, example: '8123 4567' },
];

export const toE164 = (c: Country, national: string) => `${c.dial}${national.replace(/\D/g, '')}`;

/** "+919876543210" -> "+91 98765 •••10" for display. */
export function maskPhone(e164: string): string {
  const c = [...COUNTRIES].sort((a, b) => b.dial.length - a.dial.length).find((x) => e164.startsWith(x.dial));
  const nat = c ? e164.slice(c.dial.length) : e164;
  const masked = nat.length > 4 ? `${nat.slice(0, Math.max(2, nat.length - 6))}${'•'.repeat(Math.min(4, nat.length - 4))}${nat.slice(-2)}` : nat;
  return `${c?.dial ?? ''} ${masked}`.trim();
}
