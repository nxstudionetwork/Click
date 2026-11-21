import { useEffect, useState } from 'react';

/** Click. appearance: White (default, the brand board's look) or Dark navy, or follow the device. */
export type Appearance = 'light' | 'dark' | 'system';
const KEY = 'click.appearance';

export function readAppearance(): Appearance {
  try {
    const v = localStorage.getItem(KEY);
    return v === 'dark' || v === 'system' ? v : 'light';
  } catch {
    return 'light';
  }
}

function resolve(a: Appearance): 'light' | 'dark' {
  if (a !== 'system') return a;
  return typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function applyAppearance(a: Appearance) {
  const root = document.documentElement;
  if (resolve(a) === 'dark') root.setAttribute('data-appearance', 'dark');
  else root.removeAttribute('data-appearance');
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', resolve(a) === 'dark' ? '#060B1A' : '#F8FAFC');
}

export function useAppearance() {
  const [appearance, setState] = useState<Appearance>(readAppearance);
  useEffect(() => {
    applyAppearance(appearance);
    if (appearance !== 'system' || typeof matchMedia !== 'function') return;
    const mq = matchMedia('(prefers-color-scheme: dark)');
    const on = () => applyAppearance('system');
    mq.addEventListener?.('change', on);
    return () => mq.removeEventListener?.('change', on);
  }, [appearance]);
  const setAppearance = (a: Appearance) => {
    try { localStorage.setItem(KEY, a); } catch { /* storage unavailable: applies for this visit */ }
    setState(a);
  };
  return { appearance, setAppearance };
}
