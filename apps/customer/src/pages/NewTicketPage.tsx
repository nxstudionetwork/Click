import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, SUPPORT_LINK_FIELD, type SupportCreate } from '@click/api';
import { Button, Icon, Skeleton } from '../components/ui';
import { MoneyHead, iconFor, newKey } from '../features/money/parts';
import { api } from '../lib/api';

/** Old deep links (?orderId=, ?travelBookingId=, ?bookingId=…) → the related-item type and support category. */
const LEGACY: [param: string, type: string, category: string][] = [
  ['orderId', 'order', 'order'], ['parcelId', 'parcel', 'parcel'], ['serviceBookingId', 'service_booking', 'service'], ['eventBookingId', 'event_booking', 'events'],
  ['hotelBookingId', 'hotel_booking', 'hotels'], ['travelBookingId', 'travel_booking', 'travel'], ['experienceBookingId', 'experience_booking', 'bookings'],
  ['bookingId', 'show_booking', 'shows'], ['rideId', 'ride', 'ride'], ['paymentId', 'payment', 'payment'], ['walletTransactionId', 'wallet_transaction', 'wallet'],
];
const ALIAS: Record<string, string> = { booking: 'shows', delivery: 'parcel' };
const MAX = 5 * 1024 * 1024;
const TYPES = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];

function initial(params: URLSearchParams): { category: string; related: { type: string; id: string } | null } {
  const rel = params.get('related');
  if (rel && rel.includes(':')) {
    const [type, id] = rel.split(':') as [string, string];
    return { category: ALIAS[params.get('category') ?? ''] ?? params.get('category') ?? '', related: { type, id } };
  }
  for (const [p, type, cat] of LEGACY) {
    const id = params.get(p);
    if (id) {
      const asked = params.get('category');
      return { category: !asked || asked === 'other' || asked === 'booking' ? cat : ALIAS[asked] ?? asked, related: { type, id } };
    }
  }
  const c = params.get('category') ?? '';
  return { category: ALIAS[c] ?? c, related: null };
}

/** New support request: category → issue → the order or booking it's about (only your own) → details → optional
 *  screenshot or PDF. */
export function NewTicketPage() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const start = useMemo(() => initial(params), [params]);
  const home = useQuery({ queryKey: ['help', 'home'], queryFn: api.money.support.home });
  const [category, setCategory] = useState(start.category);
  const safety = params.get('safety') === '1';
  const [issue, setIssue] = useState(params.get('issue') ?? '');
  const [urgency, setUrgency] = useState<'urgent' | 'important'>('important');
  const [contact, setContact] = useState<'call' | 'message' | 'email'>('message');
  const [related, setRelated] = useState<{ type: string; id: string } | null>(start.related);
  const [subject, setSubject] = useState(params.get('subject') ?? '');
  const [message, setMessage] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState('');
  const [key] = useState(newKey);
  const fileRef = useRef<HTMLInputElement>(null);
  const rel = useQuery({ queryKey: ['support', 'related', category], queryFn: () => api.money.support.related(category), enabled: !!category });
  useEffect(() => { if (category !== start.category) { setRelated(null); setIssue(''); } }, [category, start.category]);
  const cats = home.data?.categories ?? [];
  const issues = rel.data?.issues ?? cats.find((c) => c.code === category)?.issues ?? [];
  const items = rel.data?.results ?? [];
  const picked = related ? items.find((i) => i.type === related.type && i.id === related.id) : null;

  const create = useMutation({
    mutationFn: async () => {
      const body: SupportCreate = { category, issueType: issue || undefined, subject: subject.trim() || issue, message: message.trim(), idempotencyKey: key,
        ...(safety ? { isSafety: true, urgency, contactPreference: contact } : {}) };
      if (related && SUPPORT_LINK_FIELD[related.type]) body[SUPPORT_LINK_FIELD[related.type]!] = related.id;
      const t = await api.money.support.create(body);
      if (file) await api.money.support.send(t.id, '', file).catch(() => undefined);
      return t;
    },
    onSuccess: (t) => { qc.invalidateQueries({ queryKey: ['customer', 'support'] }); nav(`/help/tickets/${t.id}`, { replace: true, state: { created: true } }); },
    onError: (e) => {
      if (e instanceof ApiError && e.code === 'duplicate_ticket' && (e.details as { id?: string } | undefined)?.id) {
        nav(`/help/tickets/${(e.details as { id: string }).id}`, { replace: true });
        return;
      }
      setErr(e instanceof ApiError ? e.message : 'Couldn’t send. Check your connection and try again.');
    },
  });

  const pickFile = (f: File | null) => {
    setErr('');
    if (!f) return setFile(null);
    if (!TYPES.includes(f.type)) return setErr('Attach a JPEG, PNG or WebP image, or a PDF.');
    if (f.size > MAX) return setErr('Attachments can be up to 5 MB.');
    setFile(f);
  };
  const submit = () => {
    if (!category) return setErr('Choose what it’s about.');
    if (!issue && !subject.trim()) return setErr('Choose an issue or add a subject.');
    if (message.trim().length < 10) return setErr('Tell us a little more (at least 10 characters).');
    setErr('');
    create.mutate();
  };

  return (
    <div className="mn-page">
      <MoneyHead title={safety ? 'Report a safety problem' : 'Contact support'} back={safety ? '/safety' : '/help'} />
      {!home.data ? <Skeleton height={300} /> : (
        <form className="mn-form mn-card" onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <fieldset className="mn-field"><legend>What’s it about?</legend>
            <div className="mn-chips mn-chips--wrap">{cats.map((c) => (
              <button key={c.code} type="button" className="mn-chip" aria-pressed={category === c.code} onClick={() => setCategory(c.code)}><Icon name={iconFor(c.code)} size={15} />{c.label}</button>
            ))}</div>
          </fieldset>

          {category && issues.length > 0 && (
            <fieldset className="mn-field"><legend>Issue</legend>
              <div className="mn-chips mn-chips--wrap">{issues.map((i) => <button key={i} type="button" className="mn-chip" aria-pressed={issue === i} onClick={() => setIssue(i)}>{i}</button>)}</div>
            </fieldset>
          )}

          {category && (
            <label className="mn-field"><span>Related {items.length ? 'order or booking' : 'item'}</span>
              {rel.isPending ? <Skeleton height={44} /> : items.length === 0 && !related ? <span className="small mn-muted">Nothing recent to attach for this service.</span> : (
                <select value={related ? `${related.type}:${related.id}` : ''} onChange={(e) => { const [t, id] = e.target.value.split(':'); setRelated(t && id ? { type: t, id } : null); }}>
                  <option value="">Not about a specific one</option>
                  {related && !picked && <option value={`${related.type}:${related.id}`}>The item you came from</option>}
                  {items.map((i) => <option key={`${i.type}:${i.id}`} value={`${i.type}:${i.id}`}>{i.label}</option>)}
                </select>
              )}
            </label>
          )}

          <label className="mn-field"><span>Subject</span>
            <input value={subject} onChange={(e) => setSubject(e.target.value.slice(0, 120))} placeholder={issue || 'A short summary'} /></label>
          <label className="mn-field"><span>Details</span>
            <textarea rows={5} value={message} onChange={(e) => setMessage(e.target.value.slice(0, 4000))} placeholder="What happened, and what would you like us to do?" /></label>

          <div className="mn-field"><span>Attachment <span className="mn-muted small">(optional · image or PDF, up to 5 MB)</span></span>
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" hidden onChange={(e) => pickFile(e.target.files?.[0] ?? null)} />
            {file ? <div className="mn-file"><Icon name="receipt" size={18} /><span className="truncate">{file.name}</span><button type="button" className="mn-link small" onClick={() => { setFile(null); if (fileRef.current) fileRef.current.value = ''; }}>Remove</button></div>
              : <button type="button" className="btn btn--outline btn--sm" onClick={() => fileRef.current?.click()}><Icon name="camera" size={16} /> Add a screenshot or PDF</button>}
          </div>

          {err && <p className="mn-error small" role="alert">{err}</p>}
          {safety && (
            <>
              <fieldset className="mn-field"><legend>How urgent is it?</legend>
                <label className="mn-option"><input type="radio" checked={urgency === 'urgent'} onChange={() => setUrgency('urgent')} /><span>Urgent — I need help now</span></label>
                <label className="mn-option"><input type="radio" checked={urgency === 'important'} onChange={() => setUrgency('important')} /><span>Important — please look into it soon</span></label>
              </fieldset>
              <label className="mn-field"><span>How should we reach you?</span>
                <select value={contact} onChange={(e) => setContact(e.target.value as 'call' | 'message' | 'email')}>
                  <option value="message">Message in the app</option><option value="call">Call me</option><option value="email">Email</option></select></label>
              <p className="small mn-warn">In immediate danger? Call 112 first.</p>
            </>
          )}
          <Button type="submit" block loading={create.isPending}>{safety ? 'Send safety report' : 'Send request'}</Button>
          <p className="small mn-muted">Never share OTPs, UPI PINs, card numbers or passwords. Click. Support will never ask for them.</p>
        </form>
      )}
    </div>
  );
}
