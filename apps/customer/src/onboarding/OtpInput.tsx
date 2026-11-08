import { useEffect, useRef } from 'react';

/** Accessible 6-digit code input: auto-advance, backspace, paste and SMS autofill (one-time-code). */
export function OtpInput({ value, onChange, length = 6, disabled, invalid, onComplete }: {
  value: string; onChange: (v: string) => void; length?: number; disabled?: boolean; invalid?: boolean; onComplete?: (v: string) => void;
}) {
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  useEffect(() => { refs.current[0]?.focus(); }, []);
  useEffect(() => { if (invalid) refs.current[Math.min(value.length, length - 1)]?.focus(); }, [invalid, value.length, length]);

  const set = (next: string) => {
    const clean = next.replace(/\D/g, '').slice(0, length);
    onChange(clean);
    refs.current[Math.min(clean.length, length - 1)]?.focus();
    if (clean.length === length) onComplete?.(clean);
  };

  return (
    <div className={`otp ${invalid ? 'otp--invalid' : ''}`} role="group" aria-label="Verification code">
      {Array.from({ length }, (_, i) => (
        <input
          key={i}
          ref={(el) => { refs.current[i] = el; }}
          className={`otp__box ${value[i] ? 'otp__box--filled' : ''}`}
          inputMode="numeric"
          autoComplete={i === 0 ? 'one-time-code' : 'off'}
          pattern="[0-9]*"
          maxLength={i === 0 ? length : 1}
          aria-label={`Digit ${i + 1} of ${length}`}
          value={value[i] ?? ''}
          disabled={disabled}
          onChange={(e) => {
            const typed = e.target.value.replace(/\D/g, '');
            if (typed.length > 1) return set(value.slice(0, i) + typed);  // paste / SMS autofill
            set((value.slice(0, i) + typed + value.slice(i + 1)).slice(0, length));
          }}
          onKeyDown={(e) => {
            if (e.key === 'Backspace' && !value[i] && i > 0) { e.preventDefault(); set(value.slice(0, i - 1)); }
            if (e.key === 'ArrowLeft' && i > 0) refs.current[i - 1]?.focus();
            if (e.key === 'ArrowRight' && i < length - 1) refs.current[i + 1]?.focus();
          }}
          onFocus={(e) => e.target.select()}
        />
      ))}
    </div>
  );
}
