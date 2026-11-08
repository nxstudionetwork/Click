import { useId } from 'react';
import type { PartnerField } from '@click/api';
import { ChoiceChips } from './ChoiceChips';

export type FieldValue = string | string[] | number | undefined;

/** Renders one category-specific field from the server-defined schema. */
export function DynamicField({ field, value, onChange, error }: {
  field: PartnerField; value: FieldValue; onChange: (v: FieldValue) => void; error?: string;
}) {
  const id = useId();
  if (field.kind === 'multiselect' || (field.kind === 'select' && (field.options?.length ?? 0) <= 7)) {
    return (
      <ChoiceChips
        name={field.key} label={field.label} options={field.options ?? []} value={value as string | string[]}
        multiple={field.kind === 'multiselect'} onChange={onChange} error={error} required={field.required} help={field.help}
      />
    );
  }
  const common = {
    id, className: 'field__input', 'aria-invalid': !!error, required: field.required,
    'aria-describedby': [field.help && `${id}-help`, error && `${id}-err`].filter(Boolean).join(' ') || undefined,
  };
  let control;
  if (field.kind === 'select') {
    control = (
      <select {...common} value={(value as string) ?? ''} onChange={(e) => onChange(e.target.value)}>
        <option value="">Choose…</option>
        {field.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    );
  } else if (field.kind === 'textarea') {
    control = (
      <textarea {...common} rows={3} maxLength={field.maxLength} placeholder={field.placeholder}
        value={(value as string) ?? ''} onChange={(e) => onChange(e.target.value)} />
    );
  } else if (field.kind === 'number') {
    control = (
      <input {...common} type="number" inputMode="numeric" min={field.min} max={field.max} step={1}
        placeholder={field.placeholder} value={value === undefined ? '' : String(value)}
        onChange={(e) => onChange(e.target.value === '' ? undefined : e.target.value)} />
    );
  } else {
    control = (
      <input {...common} type={field.kind === 'time' ? 'time' : 'text'} maxLength={field.maxLength}
        placeholder={field.placeholder} value={(value as string) ?? ''} onChange={(e) => onChange(e.target.value)} />
    );
  }
  return (
    <div className={`field ${error ? 'field--error' : ''}`}>
      <label className="field__label" htmlFor={id}>{field.label}{!field.required && <span className="optional"> (optional)</span>}</label>
      {control}
      {field.help && <span id={`${id}-help`} className="field__help">{field.help}</span>}
      {error && <span id={`${id}-err`} className="field__error" role="alert">{error}</span>}
    </div>
  );
}
