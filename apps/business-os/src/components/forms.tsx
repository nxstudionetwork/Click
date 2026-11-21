/**
 * Spec-driven forms and tables used by every Business OS module, so screens stay consistent and accessible:
 *
 *   <FormDialog title="New position" fields={[{ name: 'title', label: 'Title', required: true }, …]} onSubmit={…} />
 *   <DataTable rows={…} columns={[{ key: 'name', label: 'Name', render: (r) => … }]} onRow={…} />
 */
import { useId, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@click/ui';
import { apiMessage, fieldErrors } from '../lib/api';
import { Alert, Dialog, Empty } from './ui';

export type FieldSpec = {
  name: string;
  label: string;
  type?: 'text' | 'textarea' | 'number' | 'date' | 'datetime-local' | 'time' | 'email' | 'select' | 'checkbox' | 'multiselect';
  options?: { value: string; label: string }[];
  required?: boolean;
  hint?: string;
  placeholder?: string;
  half?: boolean;
  min?: number;
  max?: number;
};

const camel = (s: string) => s.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());

export function FormFields({ fields, values, onChange, errors = {} }: {
  fields: FieldSpec[]; values: Record<string, unknown>; onChange: (name: string, v: unknown) => void; errors?: Record<string, string>;
}) {
  const base = useId();
  return (
    <div className="form-grid">
      {fields.map((f) => {
        const id = `${base}-${f.name}`;
        const err = errors[camel(f.name)] ?? errors[f.name];
        const v = values[f.name];
        if (f.type === 'checkbox') {
          return (
            <label key={f.name} className="row small form-grid__full">
              <input type="checkbox" checked={Boolean(v)} onChange={(e) => onChange(f.name, e.target.checked)} />{f.label}
            </label>
          );
        }
        let input: ReactNode;
        if (f.type === 'select') {
          input = (
            <select id={id} className="field__input" value={String(v ?? '')} onChange={(e) => onChange(f.name, e.target.value)} required={f.required}>
              <option value="">{f.required ? 'Choose…' : '—'}</option>
              {f.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          );
        } else if (f.type === 'multiselect') {
          const set = new Set((v as string[]) ?? []);
          input = (
            <div className="pill-list" role="group" aria-labelledby={id}>
              {f.options?.map((o) => (
                <label key={o.value} className={`pill ${set.has(o.value) ? 'pill--on' : ''}`}>
                  <input type="checkbox" className="sr-only" checked={set.has(o.value)}
                    onChange={(e) => { const n = new Set(set); if (e.target.checked) n.add(o.value); else n.delete(o.value); onChange(f.name, [...n]); }} />
                  {o.label}
                </label>
              ))}
            </div>
          );
        } else if (f.type === 'textarea') {
          input = <textarea id={id} className="field__input" rows={3} value={String(v ?? '')} placeholder={f.placeholder} onChange={(e) => onChange(f.name, e.target.value)} required={f.required} />;
        } else {
          input = <input id={id} className="field__input" type={f.type ?? 'text'} value={String(v ?? '')} placeholder={f.placeholder} min={f.min} max={f.max}
                         onChange={(e) => onChange(f.name, e.target.value)} required={f.required} />;
        }
        return (
          <div key={f.name} className={`field ${err ? 'field--error' : ''} ${f.half ? '' : 'form-grid__full'}`}>
            <label className="field__label" id={id} htmlFor={id}>{f.label}{f.required && <span aria-hidden="true"> *</span>}</label>
            {input}
            {err ? <span className="field__error">{err}</span> : f.hint && <span className="field__hint">{f.hint}</span>}
          </div>
        );
      })}
    </div>
  );
}

export function FormDialog<T = unknown>({ title, fields, initial = {}, submitLabel = 'Save', onSubmit, onClose, onDone, intro, wide }: {
  title: string; fields: FieldSpec[]; initial?: Record<string, unknown>; submitLabel?: string; intro?: ReactNode; wide?: boolean;
  onSubmit: (values: Record<string, unknown>) => Promise<T>; onClose: () => void; onDone?: (result: T) => void;
}) {
  const [values, setValues] = useState<Record<string, unknown>>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const errs = fieldErrors(error);
  const missing = fields.some((f) => f.required && f.type !== 'checkbox' && (values[f.name] === undefined || values[f.name] === ''));
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const clean = Object.fromEntries(Object.entries(values).map(([k, v]) => [camel(k), v === '' ? null : v]));
      const r = await onSubmit(clean);
      onDone?.(r);
      onClose();
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  return (
    <Dialog title={title} onClose={onClose} wide={wide} footer={<>
      <Button variant="outline" onClick={onClose}>Cancel</Button>
      <Button loading={busy} disabled={missing} onClick={() => void submit()}>{submitLabel}</Button>
    </>}>
      {intro}
      {error != null && !Object.keys(errs).length && <Alert tone="error">{apiMessage(error)}</Alert>}
      <form onSubmit={(e) => { e.preventDefault(); if (!missing) void submit(); }}>
        <FormFields fields={fields} values={values} errors={errs} onChange={(n, v) => setValues((s) => ({ ...s, [n]: v }))} />
        <button type="submit" hidden />
      </form>
    </Dialog>
  );
}

export interface Column<R> { key: string; label: string; render?: (row: R) => ReactNode; num?: boolean; width?: number | string }

export function DataTable<R extends { id?: string }>({ rows, columns, onRow, empty = 'Nothing here yet', emptyMessage, caption }: {
  rows: R[]; columns: Column<R>[]; onRow?: (row: R) => void; empty?: string; emptyMessage?: string; caption?: string;
}) {
  if (!rows.length) return <Empty title={empty} message={emptyMessage} />;
  return (
    <div className="table-wrap">
      <table className="table">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead><tr>{columns.map((c) => <th key={c.key} className={c.num ? 'num' : ''} style={{ width: c.width }} scope="col">{c.label}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id ?? i} className={onRow ? 'clickable' : ''} onClick={onRow ? () => onRow(r) : undefined}
                tabIndex={onRow ? 0 : undefined} onKeyDown={onRow ? (e) => { if (e.key === 'Enter') onRow(r); } : undefined}>
              {columns.map((c) => <td key={c.key} className={c.num ? 'num' : ''}>{c.render ? c.render(r) : String((r as Record<string, unknown>)[c.key] ?? '—')}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function StatGrid({ items }: { items: { key: string; label: string; value: ReactNode; hint?: ReactNode; to?: string; tone?: 'alert' | 'good' }[] }) {
  return (
    <div className="stat-grid">
      {items.map((s) => {
        const body = (<><span className="stat__label">{s.label}</span><strong className={`stat__value ${s.tone ? `stat__value--${s.tone}` : ''}`}>{s.value}</strong>
          {s.hint && <span className="stat__hint">{s.hint}</span>}</>);
        return s.to ? <Link key={s.key} to={s.to} className="stat stat--link">{body}</Link>
          : <div key={s.key} className="stat">{body}</div>;
      })}
    </div>
  );
}
