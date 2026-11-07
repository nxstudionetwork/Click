const formatters = new Map<string, Intl.NumberFormat>();

export function formatMoney(amount: string | number, currency = 'INR'): string {
  let f = formatters.get(currency);
  if (!f) {
    f = new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 2, minimumFractionDigits: 0 });
    formatters.set(currency, f);
  }
  return f.format(Number(amount));
}

export const priceLevelLabel = (level: number, symbol = '₹') => symbol.repeat(Math.max(1, Math.min(4, level)));

export const etaLabel = (min: number, max: number) => `${min}–${max} min`;

export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso));
}

export function formatTime(iso: string): string {
  return new Intl.DateTimeFormat('en-IN', { timeStyle: 'short' }).format(new Date(iso));
}
