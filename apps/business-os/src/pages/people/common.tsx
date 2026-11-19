/* eslint-disable @typescript-eslint/no-explicit-any */
import { useRef, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Icon, useToast } from '@click/ui';
import { apiMessage, people } from '../../lib/api';
import { fmtDate } from '../../lib/format';
import { Alert, Card, Dialog, LoadingRows, PageHeader, QueryError, Status } from '../../components/ui';

export const useLookups = () => useQuery({ queryKey: ['os', 'people', 'lookups'], queryFn: people.lookups, staleTime: 300_000 });
export const opts = (rows: { id: string; name: string }[] | undefined) => (rows ?? []).map((r) => ({ value: r.id, label: r.name }));
export const vopts = (rows: { value: string; label: string }[] | undefined) => rows ?? [];

export const STATUS_LABEL: Record<string, string> = {
  pre_onboarding: 'Pre-onboarding', active: 'Active', probation: 'Probation', confirmed: 'Confirmed', on_leave: 'On leave', suspended: 'Suspended',
  notice: 'Notice period', resigned: 'Resigned', terminated: 'Terminated', retired: 'Retired', former: 'Former employee',
};
export function EmpStatus({ value }: { value: string }) {
  const tone = ['active', 'confirmed'].includes(value) ? 'success' : ['probation', 'pre_onboarding', 'on_leave'].includes(value) ? 'info'
    : ['notice', 'suspended'].includes(value) ? 'warning' : 'neutral';
  return <Status value={value} tone={tone as 'info'} label={STATUS_LABEL[value] ?? value} />;
}

/** People & HR shell: the module's own navigation, built from what the server says this person may use. */
export function PeopleLayout() {
  const nav = useQuery({ queryKey: ['os', 'people', 'nav'], queryFn: people.nav, staleTime: 120_000 });
  return (
    <div className="module-layout">
      <nav className="sidenav" aria-label="People & HR">
        {nav.isPending ? <LoadingRows rows={6} /> : nav.error ? <QueryError error={nav.error} /> : (
          <>
            <NavLink to="/people" end><Icon name="team" size={16} />HR home</NavLink>
            {nav.data.sections.map((sec) => (
              <div key={sec.key} style={{ display: 'contents' }}>
                <div className="sidenav__label">{sec.label}</div>
                {sec.items.map((i) => <NavLink key={i.key} to={i.path.split('?')[0]!} end={i.path.includes('?')}>{i.label}</NavLink>)}
              </div>
            ))}
          </>
        )}
      </nav>
      <div style={{ minWidth: 0 }}><Outlet /></div>
    </div>
  );
}

export function SectionTitle({ title, desc, actions }: { title: string; desc?: string; actions?: React.ReactNode }) {
  return <PageHeader title={title} description={desc} crumbs={[{ label: 'People & HR', to: '/people' }, { label: title }]} actions={actions} />;
}

/** Central document store, scoped by People & HR access rules on the server. */
export function DocumentsPanel({ resourceType, resourceId, title = 'Documents' }: { resourceType: string; resourceId: string; title?: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const key = ['os', 'documents', resourceType, resourceId];
  const q = useQuery({ queryKey: key, queryFn: () => people.documents(resourceType, resourceId) });
  const [upload, setUpload] = useState(false);
  const act = useMutation({ mutationFn: ({ id, a }: { id: string; a: 'verify' | 'reject' | 'archive' }) => people.documentAction(id, a),
    onSuccess: () => void qc.invalidateQueries({ queryKey: key }), onError: (e) => toast(apiMessage(e), 'error') });
  const open = async (id: string, name: string | null) => {
    try {
      const blob = await people.downloadDocument(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.target = '_blank'; a.rel = 'noopener'; a.download = name ?? 'document';
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
    } catch (e) { toast(apiMessage(e), 'error'); }
  };
  return (
    <Card title={title} flush actions={q.data?.canUpload && <Button size="sm" onClick={() => setUpload(true)}><Icon name="plus" size={15} />Upload</Button>}>
      {q.isPending ? <LoadingRows /> : q.error ? <QueryError error={q.error} /> : !q.data.results.length ? <p className="muted small" style={{ padding: 16 }}>No documents yet.</p> : (
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Document</th><th>Sensitivity</th><th>Expires</th><th>Verification</th><th /></tr></thead>
          <tbody>{q.data.results.map((d) => (
            <tr key={d.id}>
              <td><button className="btn btn--ghost btn--sm" style={{ padding: 0 }} onClick={() => void open(d.id, d.fileName)}>{d.title}</button>
                <div className="xs muted">{d.category} · v{d.version} · {d.uploadedBy ?? '—'} · {fmtDate(d.createdAt)}</div></td>
              <td><Status value={d.sensitivity} tone={d.sensitivity === 'restricted' ? 'danger' : d.sensitivity === 'confidential' ? 'warning' : 'neutral'} /></td>
              <td className={d.expired ? 'small' : 'small muted'} style={{ color: d.expired ? 'var(--c-danger)' : d.expiring ? 'var(--c-warning)' : undefined }}>
                {d.expiresOn ? `${d.expired ? 'Expired ' : ''}${fmtDate(d.expiresOn)}` : '—'}</td>
              <td><Status value={d.verification === 'verified' ? 'active' : d.verification === 'rejected' ? 'rejected' : 'pending'} label={d.verification} /></td>
              <td className="num">{d.canVerify && d.verification !== 'verified' && <><Button size="sm" variant="ghost" onClick={() => act.mutate({ id: d.id, a: 'verify' })}>Verify</Button>
                <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: d.id, a: 'reject' })}>Reject</Button></>}</td>
            </tr>))}</tbody>
        </table></div>
      )}
      {upload && <UploadDialog resourceType={resourceType} resourceId={resourceId} onClose={() => setUpload(false)} onDone={() => void qc.invalidateQueries({ queryKey: key })} />}
    </Card>
  );
}

function UploadDialog({ resourceType, resourceId, onClose, onDone }: { resourceType: string; resourceId: string; onClose: () => void; onDone: () => void }) {
  const file = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('employment');
  const [sens, setSens] = useState('confidential');
  const [expires, setExpires] = useState('');
  const up = useMutation({
    mutationFn: () => people.uploadDocument({ resourceType, resourceId, title, category, sensitivity: sens, expiresOn: expires || undefined, file: file.current!.files![0]! }),
    onSuccess: () => { onDone(); onClose(); },
  });
  return (
    <Dialog title="Upload document" onClose={onClose} footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button loading={up.isPending} onClick={() => up.mutate()}>Upload</Button></>}>
      {up.error && <Alert tone="error">{apiMessage(up.error)}</Alert>}
      <label className="field"><span className="field__label">File (PDF, JPG, PNG, WebP or Word, up to 10 MB)</span><input ref={file} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp,.docx" className="field__input" /></label>
      <label className="field"><span className="field__label">Title</span><input className="field__input" value={title} onChange={(e) => setTitle(e.target.value)} /></label>
      <div className="form-grid">
        <label className="field"><span className="field__label">Category</span><select className="field__input" value={category} onChange={(e) => setCategory(e.target.value)}>
          {['employment', 'agreement', 'id', 'certificate', 'tax', 'policy', 'performance', 'resume', 'other'].map((c) => <option key={c} value={c}>{c}</option>)}</select></label>
        <label className="field"><span className="field__label">Sensitivity</span><select className="field__input" value={sens} onChange={(e) => setSens(e.target.value)}>
          <option value="normal">Normal</option><option value="confidential">Confidential</option><option value="restricted">Restricted (ID, tax, medical)</option></select></label>
        <label className="field form-grid__full"><span className="field__label">Expiry date (optional)</span><input type="date" className="field__input" value={expires} onChange={(e) => setExpires(e.target.value)} /></label>
      </div>
    </Dialog>
  );
}

export function Bars({ rows, max }: { rows: { label: string; value: number | null }[]; max?: number }) {
  const m = max ?? Math.max(1, ...rows.map((r) => r.value ?? 0));
  if (!rows.length) return <p className="muted small">No data yet.</p>;
  return (
    <div className="bars">
      {rows.map((r) => (
        <div key={r.label} className="bars__row"><span className="ellipsis">{r.label}</span>
          <span className="bars__track">{r.value !== null && <span style={{ width: `${(r.value / m) * 100}%` }} />}</span>
          <strong className="num" style={{ textAlign: 'right' }}>{r.value === null ? <span className="xs muted" title="Hidden to protect individuals (small group)">&lt;3</span> : r.value}</strong></div>
      ))}
    </div>
  );
}

export function useInv(...keys: string[][]) {
  const qc = useQueryClient();
  return () => keys.forEach((k) => void qc.invalidateQueries({ queryKey: k }));
}
