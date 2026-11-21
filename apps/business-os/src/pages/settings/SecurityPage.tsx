import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, TextField, useToast } from '@click/ui';
import { api, apiMessage, fieldErrors } from '../../lib/api';
import { fmtDateTime, humanize, relative } from '../../lib/format';
import { CONTEXT_KEY, useOS, useOSSession } from '../../session/OSSession';
import { Alert, Card, ConfirmDialog, Dialog, LoadingRows, QueryError, Status } from '../../components/ui';

export function SecurityPage() {
  const ctx = useOS();
  const [params] = useSearchParams();
  const [setup, setSetup] = useState(params.get('setup') === 'mfa' && !ctx.account.mfaEnabled);
  return (
    <div className="stack stack--lg">
      <MfaCard onSetup={() => setSetup(true)} />
      <PasswordCard />
      <SessionsCard />
      <ActivityCard />
      {setup && <MfaSetupDialog onClose={() => setSetup(false)} />}
    </div>
  );
}

function MfaCard({ onSetup }: { onSetup: () => void }) {
  const ctx = useOS();
  const qc = useQueryClient();
  const toast = useToast();
  const [disabling, setDisabling] = useState(false);
  const [regen, setRegen] = useState(false);
  const [pw, setPw] = useState('');
  const [code, setCode] = useState('');
  const [codes, setCodes] = useState<string[] | null>(null);
  const disable = useMutation({ mutationFn: () => api.me.mfaDisable(pw, code), onSuccess: () => { setDisabling(false); toast('Two-step verification turned off'); void qc.invalidateQueries({ queryKey: CONTEXT_KEY }); } });
  const regenerate = useMutation({ mutationFn: () => api.me.recoveryCodes(pw), onSuccess: (r) => { setRegen(false); setCodes(r.recoveryCodes); setPw(''); } });
  return (
    <Card title="Two-step verification" actions={<Status value={ctx.account.mfaEnabled ? 'active' : 'warning'} label={ctx.account.mfaEnabled ? 'On' : 'Off'} />}>
      <div className="stack">
        <p className="small">After your password, you’ll enter a 6-digit code from an authenticator app. {ctx.security.sensitiveRequiresMfa ? 'Sensitive areas (administration, payroll, sensitive audit) require it.' : ''}</p>
        {ctx.mfaBlocked.length > 0 && <Alert tone="warning">{ctx.mfaBlocked.length} of your permissions are switched off until two-step verification is on.</Alert>}
        <div className="row row--wrap">
          {ctx.account.mfaEnabled ? <>
            <Button variant="outline" onClick={() => { setRegen(true); setPw(''); }}>New recovery codes</Button>
            <Button variant="danger" onClick={() => { setDisabling(true); setPw(''); setCode(''); }}>Turn off</Button>
          </> : <Button onClick={onSetup}>Set up two-step verification</Button>}
        </div>
      </div>
      {disabling && (
        <ConfirmDialog title="Turn off two-step verification?" message="Your account will be protected by your password only, and sensitive access will switch off." confirmLabel="Turn off" danger
          busy={disable.isPending} onConfirm={() => disable.mutate()} onClose={() => setDisabling(false)}>
          {disable.error && <Alert tone="error">{apiMessage(disable.error)}</Alert>}
          <TextField label="Password" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" />
          <TextField label="Current code" value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" maxLength={6} />
        </ConfirmDialog>
      )}
      {regen && (
        <ConfirmDialog title="Generate new recovery codes" message="Your old recovery codes stop working." confirmLabel="Generate" busy={regenerate.isPending}
          onConfirm={() => regenerate.mutate()} onClose={() => setRegen(false)}>
          {regenerate.error && <Alert tone="error">{apiMessage(regenerate.error)}</Alert>}
          <TextField label="Password" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" />
        </ConfirmDialog>
      )}
      {codes && <RecoveryCodesDialog codes={codes} onClose={() => setCodes(null)} />}
    </Card>
  );
}

function RecoveryCodesDialog({ codes, onClose }: { codes: string[]; onClose: () => void }) {
  return (
    <Dialog title="Save your recovery codes" onClose={onClose} footer={<>
      <Button variant="outline" onClick={() => void navigator.clipboard?.writeText(codes.join('\n'))}>Copy</Button>
      <Button onClick={onClose}>I’ve saved them</Button>
    </>}>
      <p className="small">Each code works once if you lose access to your authenticator app. Store them somewhere safe. They won’t be shown again.</p>
      <div className="recovery">{codes.map((c) => <span key={c}>{c}</span>)}</div>
    </Dialog>
  );
}

function MfaSetupDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const setup = useQuery({ queryKey: ['os', 'mfa-setup'], queryFn: api.me.mfaSetup, staleTime: Infinity, gcTime: 0, retry: false });
  const [code, setCode] = useState('');
  const [codes, setCodes] = useState<string[] | null>(null);
  const confirm = useMutation({ mutationFn: () => api.me.mfaConfirm(code), onSuccess: (r) => { setCodes(r.recoveryCodes); void qc.invalidateQueries({ queryKey: CONTEXT_KEY }); } });
  if (codes) return <RecoveryCodesDialog codes={codes} onClose={onClose} />;
  return (
    <Dialog title="Set up two-step verification" onClose={onClose} footer={<>
      <Button variant="outline" onClick={onClose}>Cancel</Button>
      <Button loading={confirm.isPending} disabled={code.trim().length !== 6} onClick={() => confirm.mutate()}>Verify and turn on</Button>
    </>}>
      {setup.isPending ? <LoadingRows /> : setup.error ? <QueryError error={setup.error} /> : (
        <>
          <ol className="small stack" style={{ paddingLeft: 18, margin: 0, gap: 6 }}>
            <li>Open your authenticator app and add an account (choose “enter a setup key”).</li>
            <li>Enter this key, time-based: <div className="secret" style={{ marginTop: 6 }}>{setup.data.secret.replace(/(.{4})/g, '$1 ').trim()}</div>
              <span className="xs muted">On a phone you can also <a href={setup.data.otpauthUri}>open it in your authenticator</a>.</span></li>
            <li>Enter the 6-digit code it shows.</li>
          </ol>
          {confirm.error && <Alert tone="error">{apiMessage(confirm.error)}</Alert>}
          <TextField label="6-digit code" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} inputMode="numeric" maxLength={6} autoComplete="one-time-code" />
        </>
      )}
    </Dialog>
  );
}

function PasswordCard() {
  const toast = useToast();
  const [cur, setCur] = useState('');
  const [next, setNext] = useState('');
  const [next2, setNext2] = useState('');
  const change = useMutation({
    mutationFn: () => api.me.changePassword(cur, next),
    onSuccess: (r) => { setCur(''); setNext(''); setNext2(''); toast(`Password changed${r.otherSessionsEnded ? `; ${r.otherSessionsEnded} other device(s) signed out` : ''}`); },
  });
  const errs = fieldErrors(change.error);
  return (
    <Card title="Password">
      <form className="stack" style={{ maxWidth: 420 }} onSubmit={(e) => { e.preventDefault(); change.mutate(); }}>
        {change.error && !Object.keys(errs).length && <Alert tone="error">{apiMessage(change.error)}</Alert>}
        <TextField label="Current password" type="password" value={cur} onChange={(e) => setCur(e.target.value)} error={errs.currentPassword} autoComplete="current-password" />
        <TextField label="New password" type="password" value={next} onChange={(e) => setNext(e.target.value)} error={errs.newPassword} autoComplete="new-password" />
        <TextField label="Confirm new password" type="password" value={next2} onChange={(e) => setNext2(e.target.value)} autoComplete="new-password"
                   error={next2 && next !== next2 ? 'The passwords don’t match.' : undefined} />
        <div><Button type="submit" loading={change.isPending} disabled={!cur || !next || next !== next2}>Change password</Button></div>
        <p className="xs muted">Changing your password signs out your other devices.</p>
      </form>
    </Card>
  );
}

function SessionsCard() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { logout } = useOSSession();
  const toast = useToast();
  const q = useQuery({ queryKey: ['os', 'sessions'], queryFn: api.me.sessions });
  const [confirmAll, setConfirmAll] = useState(false);
  const revoke = useMutation({ mutationFn: api.me.revokeSession, onSuccess: () => { toast('Device signed out'); void qc.invalidateQueries({ queryKey: ['os', 'sessions'] }); } });
  const all = useMutation({ mutationFn: api.auth.logoutAll, onSuccess: async () => { await logout(); navigate('/login', { replace: true }); } });
  return (
    <Card title="Signed-in devices" flush actions={<Button size="sm" variant="danger" onClick={() => setConfirmAll(true)}>Sign out everywhere</Button>}>
      {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : (
        <ul className="list">
          {q.data.results.map((s) => (
            <li key={s.id} className="list-row">
              <div className="list-row__main">
                <span className="list-row__title" style={{ display: 'block' }}>{s.deviceLabel || 'Unknown device'} {s.current && <Status value="active" label="This device" />}</span>
                <span className="list-row__sub" style={{ display: 'block' }}>{s.ip ?? 'unknown network'} · signed in {fmtDateTime(s.createdAt)} · active {relative(s.lastSeenAt)}{s.mfaVerified ? ' · 2-step verified' : ''}</span>
              </div>
              {!s.current && <Button size="sm" variant="outline" loading={revoke.isPending && revoke.variables === s.id} onClick={() => revoke.mutate(s.id)}>Sign out</Button>}
            </li>
          ))}
        </ul>
      )}
      {confirmAll && <ConfirmDialog title="Sign out of every device?" message="All Business OS sessions end immediately, including this one." confirmLabel="Sign out everywhere" danger
        busy={all.isPending} onConfirm={() => all.mutate()} onClose={() => setConfirmAll(false)} />}
    </Card>
  );
}

function ActivityCard() {
  const q = useQuery({ queryKey: ['os', 'my-activity'], queryFn: api.me.activity });
  return (
    <Card title="Recent account activity" flush>
      {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : !q.data.results.length ? <p className="muted small" style={{ padding: 16 }}>No activity yet.</p> : (
        <div className="table-wrap"><table className="table">
          <thead><tr><th>When</th><th>Activity</th><th>Result</th><th>Network</th></tr></thead>
          <tbody>{q.data.results.slice(0, 15).map((a) => (
            <tr key={a.id}><td className="muted">{fmtDateTime(a.createdAt)}</td><td>{humanize(a.action)}{a.metadata.device ? <span className="xs muted"> · {String(a.metadata.device)}</span> : null}</td>
              <td><Status value={a.outcome} /></td><td className="muted mono">{a.ip ?? '—'}</td></tr>
          ))}</tbody>
        </table></div>
      )}
    </Card>
  );
}
