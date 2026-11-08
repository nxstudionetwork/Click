import { useId, type InputHTMLAttributes, type TextareaHTMLAttributes } from 'react';

interface BaseProps {
  label: string;
  error?: string;
}

export function TextField({ label, error, id, className = '', ...rest }: BaseProps & InputHTMLAttributes<HTMLInputElement>) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <div className={`field ${error ? 'field--error' : ''} ${className}`}>
      <label className="field__label" htmlFor={inputId}>{label}</label>
      <input id={inputId} className="field__input" aria-invalid={!!error} aria-describedby={error ? `${inputId}-err` : undefined} {...rest} />
      {error && <span id={`${inputId}-err`} className="field__error">{error}</span>}
    </div>
  );
}

export function TextArea({ label, error, id, className = '', ...rest }: BaseProps & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <div className={`field ${error ? 'field--error' : ''} ${className}`}>
      <label className="field__label" htmlFor={inputId}>{label}</label>
      <textarea id={inputId} className="field__input" aria-invalid={!!error} {...rest} />
      {error && <span className="field__error">{error}</span>}
    </div>
  );
}
