const formatters = new Map<string, Intl.NumberFormat>();

/** ₹249 for whole amounts, ₹7.20 (never ₹7.2) when there are paise. */
export function formatMoney(amount: string | number, currency = 'INR'): string {
  const n = Number(amount);
  const fractional = Math.round(n * 100) % 100 !== 0;
  const key = `${currency}:${fractional}`;
  let f = formatters.get(key);
  if (!f) {
    f = new Intl.NumberFormat('en-IN', { style: 'currency', currency, minimumFractionDigits: fractional ? 2 : 0, maximumFractionDigits: 2 });
    formatters.set(key, f);
  }
  return f.format(n);
}

export const priceLevelLabel = (level: number, symbol = '₹') => symbol.repeat(Math.max(1, Math.min(4, level)));

export const etaLabel = (min: number, max: number) => `${min}–${max} min`;

export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso));
}

export function formatTime(iso: string): string {
  return new Intl.DateTimeFormat('en-IN', { timeStyle: 'short' }).format(new Date(iso));
}
