import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { STEP_ROUTE } from '../session/steps';
import { usePartnerSession } from '../session/PartnerSession';

/**
 * DEVELOPMENT ONLY. Rendered behind import.meta.env.DEV (removed from production builds); the backend endpoint is
 * 404 unless DEBUG. Signs in as a seeded test partner so every category's Home can be reviewed without SMS.
 */
export function DevPartnerLogin() {
  const { devSignIn } = usePartnerSession();
  const navigate = useNavigate();
  const info = useQuery({ queryKey: ['partner-dev-login'], queryFn: api.partner.devLoginInfo, retry: false });
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!info.data?.enabled) return null;

  async function signIn() {
    if (!code) return;
    setBusy(true);
    setError(null);
    try {
      const s = await devSignIn(code);
      navigate(STEP_ROUTE[s.onboardingStep], { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Dev login failed');
    } finally {
      setBusy(false);
    }
  }
  const partners = info.data.partners;

  return (
    <section className="dev-panel" aria-label="Development login">
      <span className="dev-panel__tag">Development mode</span>
      {partners.length === 0 ? <p className="small">Run <code>python manage.py seed_dev_data</code> to create test partners.</p> : (
        <div className="dev-panel__row">
          <label className="visually-hidden" htmlFor="dev-partner">Test partner</label>
          <select id="dev-partner" className="field__input" value={code} onChange={(e) => setCode(e.target.value)}>
            <option value="">Choose a test partner…</option>
            {partners.map((p) => <option key={p.code} value={p.code}>{p.category} · {p.name} ({p.code})</option>)}
          </select>
          <button type="button" className="btn btn--outline" disabled={!code || busy} onClick={signIn}>
            {busy ? 'Signing in…' : 'Login as test partner'}
          </button>
        </div>
      )}
      {error && <p className="small" role="alert">{error}</p>}
    </section>
  );
}
