const DATE = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
const DATETIME = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' });
const TIME = new Intl.DateTimeFormat('en-IN', { hour: 'numeric', minute: '2-digit' });

export const fmtDate = (iso?: string | null) => (iso ? DATE.format(new Date(iso)) : '—');
export const fmtDateTime = (iso?: string | null) => (iso ? DATETIME.format(new Date(iso)) : '—');
export const fmtTime = (iso?: string | null) => (iso ? TIME.format(new Date(iso)) : '—');

export function fmtMoney(value: string | number | null | undefined, currency = 'INR'): string {
  if (value === null || value === undefined || value === '') return '—';
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 0 }).format(Number(value));
}

export function fmtNumber(v: string | number | null | undefined): string {
  return v === null || v === undefined ? '—' : new Intl.NumberFormat('en-IN').format(Number(v));
}

export function relative(iso?: string | null): string {
  if (!iso) return '—';
  const diff = (new Date(iso).getTime() - Date.now()) / 1000;
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });
  if (abs < 60) return 'just now';
  if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour');
  if (abs < 86400 * 7) return rtf.format(Math.round(diff / 86400), 'day');
  return fmtDate(iso);
}

export function initials(name?: string | null): string {
  const parts = (name ?? '').trim().split(/\s+/).filter(Boolean);
  const first = parts[0]?.[0] ?? '';
  const last = parts.length > 1 ? parts[parts.length - 1]?.[0] ?? '' : '';
  return (first + last).toUpperCase() || '·';
}

export const humanize = (s: string) => s.replace(/[_.]/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

export const SCOPE_LABEL: Record<string, string> = {
  organization: 'Entire organization', units: 'Your locations', department: 'Your department', team: 'Your team',
  partner: 'Your partner business', own: 'Own records', none: 'No access',
};

/** Local datetime-input value → ISO string (or null). */
export function fromLocalInput(v: string): string | null {
  return v ? new Date(v).toISOString() : null;
}
