import { ApiError } from '@click/api';

export function formatPhone(e164: string) {
  const m = /^\+91(\d{5})(\d{5})$/.exec(e164);
  return m ? `+91 ${m[1]} ${m[2]}` : e164;
}

export function greeting(date = new Date()) {
  const h = date.getHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
}

/** Friendly message for an API failure; backend messages are already user-safe. */
export function apiMessage(err: unknown, fallback = 'Something went wrong. Please try again.') {
  if (err instanceof ApiError) {
    if (err.status === 0) return 'We can’t reach Click right now. Check your connection and try again.';
    if (err.status >= 500 && (err.code === 'server_error' || err.code === 'http_error')) return 'Click is having trouble right now. Please try again in a moment.';
    return err.code === 'validation_error' ? 'Please check the highlighted fields.' : err.message;
  }
  return fallback;
}

/** Flattens `{field: ["msg"]}` and nested `{details: {field: ["msg"]}}` validation errors. */
export function fieldErrors(err: unknown, nestedKey?: string): Record<string, string> {
  if (!(err instanceof ApiError) || err.code !== 'validation_error' || !err.details) return {};
  const source = (nestedKey ? err.details[nestedKey] : err.details) as Record<string, unknown> | undefined;
  if (!source || typeof source !== 'object') return {};
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(source)) {
    if (Array.isArray(v)) out[k] = String(v[0]);
    else if (typeof v === 'string') out[k] = v;
  }
  return out;
}
