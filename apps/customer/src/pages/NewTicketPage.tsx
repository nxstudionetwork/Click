import { useState, type FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, type SupportCategory } from '@click/api';
import { Button, TextArea, TextField } from '../components/ui';
import { HELP_TOPICS } from '../features/support/faq';
import { api } from '../lib/api';

export function NewTicketPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [category, setCategory] = useState<SupportCategory>((HELP_TOPICS.find((t) => t.id === params.get('category'))?.id) ?? 'order');
  const [orderId, setOrderId] = useState(params.get('orderId') ?? '');
  const parcelId = params.get('parcelId');
  const serviceBookingId = params.get('serviceBookingId');
  const eventBookingId = params.get('eventBookingId');
  const hotelBookingId = params.get('hotelBookingId');
  const [subject, setSubject] = useState(params.get('subject') ?? '');
  const [message, setMessage] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const orders = useQuery({ queryKey: ['customer', 'orders', 'list', 'support'], queryFn: () => api.customer.orders.list() });

  const create = useMutation({
    mutationFn: api.customer.support.create,
    onSuccess: (t) => { qc.invalidateQueries({ queryKey: ['customer', 'support'] }); qc.invalidateQueries({ queryKey: ['customer', 'notifications'] }); navigate(`/help/tickets/${t.id}`, { replace: true, state: { created: true } }); },
    onError: (e) => setErrors(e instanceof ApiError ? { ...e.fieldErrors(), _: e.code === 'validation_error' ? '' : e.message } : { _: 'Could not send your request.' }),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const missing: Record<string, string> = {};
    if (!subject.trim()) missing.subject = 'Required';
    if (!message.trim()) missing.message = 'Required';
    setErrors(missing);
    if (!Object.keys(missing).length) create.mutate({ category, subject: subject.trim(), message: message.trim(), orderId: parcelId || serviceBookingId || eventBookingId || hotelBookingId ? null : orderId || null, parcelId: parcelId || null, serviceBookingId: serviceBookingId || null, eventBookingId: eventBookingId || null, hotelBookingId: hotelBookingId || null });
  }

  return (
    <form className="card card--pad stack" onSubmit={submit} noValidate style={{ maxWidth: 640 }}>
      <h1>Contact support</h1>
      <div className="field">
        <span className="field__label">Topic</span>
        <div className="chips" style={{ flexWrap: 'wrap' }}>
          {HELP_TOPICS.map((t) => <button type="button" key={t.id} className="chip" aria-pressed={category === t.id} onClick={() => setCategory(t.id)}>{t.label}</button>)}
        </div>
      </div>
      {parcelId ? <p className="small muted">About your parcel {subject.split(' · ').pop()}</p> : serviceBookingId ? <p className="small muted">About your service booking {subject.split(' · ').pop()}</p> : eventBookingId ? <p className="small muted">About your event booking {subject.split(' · ').pop()}</p> : hotelBookingId ? <p className="small muted">About your hotel booking {subject.split(' · ').pop()}</p> : <div className="field">
        <label className="field__label" htmlFor="ticket-order">Related order (optional)</label>
        <select id="ticket-order" className="field__input" value={orderId} onChange={(e) => setOrderId(e.target.value)}>
          <option value="">No specific order</option>
          {orders.data?.results.map((o) => <option key={o.id} value={o.id}>{o.number} · {o.store.name}</option>)}
        </select>
        {errors.orderId && <span className="field__error">{errors.orderId}</span>}
      </div>}
      <TextField label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} error={errors.subject} maxLength={150} />
      <TextArea label="How can we help?" value={message} onChange={(e) => setMessage(e.target.value)} error={errors.message} maxLength={4000} rows={6} />
      {errors._ && <p className="field__error" role="alert">{errors._}</p>}
      <Button type="submit" loading={create.isPending} style={{ alignSelf: 'flex-start' }}>Send request</Button>
    </form>
  );
}
