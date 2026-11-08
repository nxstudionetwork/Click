import { useId } from 'react';

/** Supported dialling regions. India only for now; adding a country is a data change here. */
export const COUNTRIES = [{ iso: 'IN', dial: '+91', flag: '🇮🇳', digits: 10, pattern: /^[6-9]\d{9}$/, example: '98765 43210' }] as const;
export type Country = (typeof COUNTRIES)[number];

export function toE164(country: Country, national: string) {
  return `${country.dial}${national}`;
}

export function validateNational(country: Country, national: string): string | null {
  if (!national) return 'Enter your mobile number.';
  if (national.length !== country.digits) return `Enter all ${country.digits} digits of your mobile number.`;
  if (!country.pattern.test(national)) return 'That mobile number doesn’t look right.';
  return null;
}

export function formatNational(digits: string) {
  return digits.length > 5 ? `${digits.slice(0, 5)} ${digits.slice(5)}` : digits;
}

export function PhoneField({ country, value, onChange, error, disabled }: {
  country: Country; value: string; onChange: (digits: string) => void; error?: string | null; disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className={`field ${error ? 'field--error' : ''}`}>
      <label className="field__label" htmlFor={id}>Mobile number</label>
      <div className="phone">
        <span className="phone__country" aria-label={`Country code ${country.dial}, India`}>
          <span aria-hidden="true">{country.flag}</span> {country.dial}
        </span>
        <input
          id={id} className="phone__input" type="tel" inputMode="numeric" autoComplete="tel-national"
          placeholder={country.example} value={formatNational(value)} disabled={disabled}
          aria-invalid={!!error} aria-describedby={error ? `${id}-err` : undefined}
          onChange={(e) => onChange(e.target.value.replace(/\D/g, '').replace(/^0+/, '').slice(0, country.digits))}
        />
      </div>
      {error && <span id={`${id}-err`} className="field__error" role="alert">{error}</span>}
    </div>
  );
}
