import { forwardRef, useId, useState } from 'react';

export const OTP_LENGTH = 6;

/**
 * One real input (so SMS autofill / paste / screen readers work) drawn as six boxes.
 */
export const OtpInput = forwardRef<HTMLInputElement, {
  value: string; onChange: (v: string) => void; error?: string | null; disabled?: boolean; onComplete?: (v: string) => void;
}>(function OtpInput({ value, onChange, error, disabled, onComplete }, ref) {
  const id = useId();
  const [focused, setFocused] = useState(false);
  return (
    <div className={`field ${error ? 'field--error' : ''}`}>
      <label className="field__label" htmlFor={id}>6-digit verification code</label>
      <div className={`otp ${focused ? 'is-focused' : ''} ${error ? 'is-error' : ''}`}>
        <input
          ref={ref} id={id} className="otp__input" type="text" inputMode="numeric" autoComplete="one-time-code"
          pattern="[0-9]*" maxLength={OTP_LENGTH} value={value} disabled={disabled}
          aria-invalid={!!error} aria-describedby={error ? `${id}-err` : undefined}
          onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
          onChange={(e) => {
            const v = e.target.value.replace(/\D/g, '').slice(0, OTP_LENGTH);
            onChange(v);
            if (v.length === OTP_LENGTH) onComplete?.(v);
          }}
        />
        <div className="otp__cells" aria-hidden="true">
          {Array.from({ length: OTP_LENGTH }, (_, i) => (
            <span key={i} className={`otp__cell ${focused && i === Math.min(value.length, OTP_LENGTH - 1) ? 'is-active' : ''} ${value[i] ? 'is-filled' : ''}`}>
              {value[i] ?? ''}
            </span>
          ))}
        </div>
      </div>
      {error && <span id={`${id}-err`} className="field__error" role="alert">{error}</span>}
    </div>
  );
});
