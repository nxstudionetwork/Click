import { useId } from 'react';
import { COUNTRIES as ALL_COUNTRIES, type Country } from '@click/phone-auth';

/** Countries Click Partner operates in. The dialling data itself is shared with every Click app. */
export const PARTNER_COUNTRY_CODES = ['IN'];
export const COUNTRIES: Country[] = ALL_COUNTRIES.filter((c) => PARTNER_COUNTRY_CODES.includes(c.iso));

const digitsFor = (country: Country) => country.example.replace(/\D/g, '').length;

export function validateNational(country: Country, national: string): string | null {
  const digits = digitsFor(country);
  if (!national) return 'Enter your mobile number.';
  if (national.length !== digits) return `Enter all ${digits} digits of your mobile number.`;
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
        <span className="phone__country" aria-label={`Country code ${country.dial}, ${country.name}`}>
          <span aria-hidden="true">{country.flag}</span> {country.dial}
        </span>
        <input
          id={id} className="phone__input" type="tel" inputMode="numeric" autoComplete="tel-national"
          placeholder={country.example} value={formatNational(value)} disabled={disabled}
          aria-invalid={!!error} aria-describedby={error ? `${id}-err` : undefined}
          onChange={(e) => onChange(e.target.value.replace(/\D/g, '').replace(/^0+/, '').slice(0, digitsFor(country)))}
        />
      </div>
      {error && <span id={`${id}-err`} className="field__error" role="alert">{error}</span>}
    </div>
  );
}
