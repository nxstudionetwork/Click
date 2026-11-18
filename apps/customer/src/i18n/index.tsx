import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthProvider';
import { api } from '../lib/api';
import { en, type Key } from './en';
import { hi } from './hi';
import { te } from './te';

/**
 * Click. internationalisation. Strings live in per-language dictionaries (en is the source of truth and complete;
 * other languages fall back to English key by key, never to an empty string). The chosen language is stored on the
 * customer's account (/customer/preferences) and mirrored locally for signed-out screens. Add a language by adding a
 * dictionary here and its code to the backend's CustomerProfile.language choices; only languages with a dictionary
 * are offered.
 */
export const DICTIONARIES = { en, hi, te } as const;
export type Lang = keyof typeof DICTIONARIES;
export const LANGUAGES: { code: Lang; label: string }[] = [{ code: 'en', label: 'English' }, { code: 'hi', label: 'हिन्दी' }, { code: 'te', label: 'తెలుగు' }];
const KEY = 'click.lang';

type Vars = Record<string, string | number>;
interface I18n { lang: Lang; setLang: (l: Lang) => void; t: (k: Key, vars?: Vars) => string }

const Ctx = createContext<I18n>({ lang: 'en', setLang: () => {}, t: (k) => en[k] });

function readLocal(): Lang {
  try { const v = localStorage.getItem(KEY); return v && v in DICTIONARIES ? (v as Lang) : 'en'; } catch { return 'en'; }
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const [lang, setLangState] = useState<Lang>(readLocal);
  const prefs = useQuery({ queryKey: ['customer', 'preferences'], queryFn: api.money.preferences.get, enabled: status === 'authenticated', staleTime: 5 * 60_000 });
  useEffect(() => { const server = prefs.data?.language; if (server && server in DICTIONARIES && server !== lang) setLangState(server as Lang); }, [prefs.data?.language]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    document.documentElement.lang = lang;
    try { localStorage.setItem(KEY, lang); } catch { /* private mode */ }
  }, [lang]);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    if (status === 'authenticated') void api.money.preferences.set({ language: l }).catch(() => undefined);
  }, [status]);
  const t = useCallback((k: Key, vars?: Vars) => {
    let s: string = (DICTIONARIES[lang] as Partial<Record<Key, string>>)[k] ?? en[k] ?? k;
    if (vars) for (const [n, v] of Object.entries(vars)) s = s.replaceAll(`{${n}}`, String(v));
    return s;
  }, [lang]);
  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useI18n = () => useContext(Ctx);
export const useT = () => useContext(Ctx).t;
