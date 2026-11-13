const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 });
const inr2 = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Money arrives as decimal strings from the API; never computed on the client. */
export function formatMoney(value: string | number | null | undefined, exact = false) {
  const n = Number(value ?? 0);
  return (exact ? inr2 : inr).format(Number.isFinite(n) ? n : 0);
}

export function timeAgo(iso: string | null | undefined, now = Date.now()) {
  if (!iso) return '';
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 45) return 'just now';
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

export function clockTime(iso: string | null | undefined) {
  return iso ? new Date(iso).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' }) : '';
}

/** "1 order", "2 orders", "1 trip completed" from a plural label the server provides. */
export function countOf(n: number, pluralLabel: string) {
  return `${n} ${n === 1 ? pluralLabel.replace(/s\b/, '') : pluralLabel}`;
}
