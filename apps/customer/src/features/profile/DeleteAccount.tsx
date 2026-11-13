import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { phoneAuth, PhoneAuthError, type PhoneVerification } from '@click/phone-auth';
import { useAuth } from '../../auth/AuthProvider';
import { Button, Sheet } from '../../components/ui';
import { api } from '../../lib/api';

/** Delete account: shows what must be finished first, needs a fresh code on the account's phone, then the backend
 *  deactivates and anonymises the account (orders, payments and invoices stay as legal records). */
export function DeleteAccount({ onDone }: { onDone?: () => void }) {
  const { logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [understood, setUnderstood] = useState(false);
  const [reason, setReason] = useState('');
  const [pending, setPending] = useState<PhoneVerification | null>(null);
  const [code, setCode] = useState('');
  const [err, setErr] = useState('');
  const info = useQuery({ queryKey: ['account', 'delete'], queryFn: api.money.account.deletion, enabled: open });
  const del = useMutation({
    mutationFn: async () => { const cred = await pending!.confirm(code); return api.money.account.delete(cred.token, reason); },
    onSuccess: async () => { await logout().catch(() => undefined); onDone?.(); nav('/login', { replace: true }); },
    onError: (e) => setErr(e instanceof ApiError || e instanceof PhoneAuthError ? e.message : 'Couldn’t delete the account. Nothing was changed.'),
  });
  const send = async () => {
    setErr('');
    try { setPending(await phoneAuth.start(info.data!.phone)); } catch (e) { setErr(e instanceof PhoneAuthError ? e.message : 'Couldn’t send the code.'); }
  };
  const blocked = (info.data?.blockers.length ?? 0) > 0;
  return (
    <>
      <button type="button" className="link-btn small" style={{ color: 'var(--c-danger)' }} onClick={() => setOpen(true)}>Delete account</button>
      <Sheet open={open} onClose={() => setOpen(false)} label="Delete your Click. account">
        <div className="psheet stack">
          <h2>Delete your Click. account?</h2>
          {!info.data ? <p className="muted">Checking your account…</p> : blocked ? (
            <>
              <p>Finish these first:</p>
              <ul className="stack" style={{ gap: 6 }}>{info.data.blockers.map((b) => <li key={b.code}><Link to={b.link} onClick={() => setOpen(false)}>{b.message}</Link></li>)}</ul>
            </>
          ) : !info.data.phone ? <p>Your account has no verified phone, so it can’t be re-verified here. <Link to="/help/new?category=account">Contact support</Link>.</p> : (
            <>
              <p className="small muted">Your name, email, phone, photo, addresses and saved items are removed and you’re signed out everywhere. {info.data.keeps} This can’t be undone.</p>
              <label className="row small" style={{ gap: 8 }}><input type="checkbox" checked={understood} onChange={(e) => setUnderstood(e.target.checked)} /> I understand my account will be permanently deleted.</label>
              <label className="field"><span className="field__label">Why are you leaving? (optional)</span>
                <input className="input" value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} /></label>
              {!pending ? <Button variant="outline" disabled={!understood} onClick={send}>Send a code to my phone</Button> : (
                <>
                  <label className="field"><span className="field__label">6-digit code</span>
                    <input className="input" inputMode="numeric" autoComplete="one-time-code" value={code} maxLength={6} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} /></label>
                  <Button variant="danger" disabled={code.length !== 6} loading={del.isPending} onClick={() => del.mutate()}>Delete my account</Button>
                </>
              )}
            </>
          )}
          {err && <p className="field__error" role="alert">{err}</p>}
        </div>
      </Sheet>
    </>
  );
}
