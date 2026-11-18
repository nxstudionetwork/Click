import { useState } from 'react';
import { Button, Icon, Skeleton, useToast } from '@click/ui';
import type { PartnerDocumentStatus } from '@click/api';
import { AppShell } from '../components/AppShell';
import { useDocuments, useSubmitDocument } from '../features/driver/queries';
import { apiMessage, fieldErrors } from '../lib/format';

const TONE: Record<string, string> = { verified: 'success', pending: 'info', expiring: 'urgent', expired: 'urgent', rejected: 'urgent', missing: 'muted' };

function DocumentRow({ doc }: { doc: PartnerDocumentStatus }) {
  const submit = useSubmitDocument();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [number, setNumber] = useState('');
  const [expiresOn, setExpiresOn] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});

  return (
    <li className={`work work--${TONE[doc.state] ?? 'info'}`}>
      <div className="work__head">
        <span className="work__icon" aria-hidden="true"><Icon name="card" size={20} /></span>
        <div className="work__title">
          <h3>{doc.label}{!doc.required && <span className="small muted"> (optional)</span>}</h3>
          <p className="muted small">{[doc.number, doc.expiresOn && `valid until ${new Date(doc.expiresOn).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}`].filter(Boolean).join(' · ') || doc.help}</p>
        </div>
        <div className="work__meta"><span className={`tag tag--${TONE[doc.state] ?? 'info'}`}>{doc.stateLabel}</span></div>
      </div>
      {doc.reviewNote && <p className="small muted">Click: {doc.reviewNote}</p>}
      {doc.canSubmit && !open && (
        <div className="work__actions"><Button size="sm" variant="outline" onClick={() => setOpen(true)}>
          {doc.state === 'missing' ? 'Add details' : 'Submit renewed document'}</Button></div>
      )}
      {open && (
        <form className="editor" noValidate onSubmit={(e) => {
          e.preventDefault();
          setErrors({});
          submit.mutate({ key: doc.key, number, expiresOn: doc.expires ? expiresOn : undefined }, {
            onSuccess: () => { setOpen(false); toast(`${doc.label} sent to Click for review`); },
            onError: (err) => { const f = fieldErrors(err); setErrors(Object.keys(f).length ? f : { form: apiMessage(err) }); },
          });
        }}>
          <div className="editor__grid">
            <label className="field"><span className="field__label">Document number</span>
              <input className="field__input" value={number} onChange={(e) => setNumber(e.target.value)} maxLength={40} autoComplete="off" />
              {errors.number && <span className="field__error">{errors.number}</span>}</label>
            {doc.expires && (
              <label className="field"><span className="field__label">Valid until</span>
                <input className="field__input" type="date" value={expiresOn} onChange={(e) => setExpiresOn(e.target.value)} />
                {errors.expiresOn && <span className="field__error">{errors.expiresOn}</span>}</label>
            )}
          </div>
          {errors.form && <p className="field__error" role="alert">{errors.form}</p>}
          <p className="small muted">Click checks the original during verification. Only the last 4 characters are shown back here.</p>
          <div className="dialog__actions">
            <button type="button" className="btn btn--ghost" onClick={() => setOpen(false)}>Cancel</button>
            <Button type="submit" size="sm" loading={submit.isPending}>Send for review</Button>
          </div>
        </form>
      )}
    </li>
  );
}

/** Verification documents for any partner type. Expired required documents stop work until renewed. */
export function DocumentsPage() {
  const q = useDocuments();
  return (
    <AppShell>
      <div className="page">
        <div className="page__head"><h1>Documents</h1><p className="muted small">What Click needs to verify you, and the status of each.</p></div>
        {q.data?.blockedReason && (
          <div className="notice notice--warning" role="alert"><Icon name="alert" size={18} /><span>{q.data.blockedReason}</span></div>
        )}
        {q.isPending ? <Skeleton height={200} radius={20} /> : q.isError ? (
          <div className="dash__error" role="alert"><h2>Couldn’t load documents</h2><p className="muted">{apiMessage(q.error)}</p>
            <Button onClick={() => void q.refetch()}>Try again</Button></div>
        ) : q.data.documents.length === 0 ? <p className="muted">Your partner type doesn’t need documents in the app.</p> : (
          <ul className="work-list">{q.data.documents.map((d) => <DocumentRow key={d.key} doc={d} />)}</ul>
        )}
      </div>
    </AppShell>
  );
}
