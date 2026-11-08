import type { PartnerFieldOption } from '@click/api';
import { Icon } from '@click/ui';

/** Radio (single) or checkbox (multiple) group rendered as large, touch-friendly chips. */
export function ChoiceChips({ name, label, options, value, multiple, onChange, error, required, help }: {
  name: string; label: string; options: PartnerFieldOption[]; value: string | string[] | undefined;
  multiple?: boolean; onChange: (v: string | string[]) => void; error?: string; required?: boolean; help?: string;
}) {
  const selected = new Set(Array.isArray(value) ? value : value ? [value] : []);
  const toggle = (v: string) => {
    if (!multiple) return onChange(v);
    const next = new Set(selected);
    if (next.has(v)) next.delete(v);
    else next.add(v);
    onChange(options.map((o) => o.value).filter((o) => next.has(o)));
  };
  return (
    <fieldset className={`field choice ${error ? 'field--error' : ''}`} aria-invalid={!!error || undefined}>
      <legend className="field__label">{label}{!required && <span className="optional"> (optional)</span>}</legend>
      {help && <span className="field__help">{help}</span>}
      <div className="choice__list">
        {options.map((o) => {
          const checked = selected.has(o.value);
          return (
            <label key={o.value} className={`choice__chip ${checked ? 'is-checked' : ''}`}>
              <input type={multiple ? 'checkbox' : 'radio'} name={name} value={o.value} checked={checked} onChange={() => toggle(o.value)} />
              {checked && <Icon name="check" size={16} />}
              {o.label}
            </label>
          );
        })}
      </div>
      {error && <span className="field__error" role="alert">{error}</span>}
    </fieldset>
  );
}
