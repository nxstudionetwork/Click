import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthProvider';
import { EmptyState, ErrorState, Icon, Skeleton } from '../components/ui';
import { MoneyHead, Pill, Section, dateOf, iconFor } from '../features/money/parts';
import { api } from '../lib/api';

const QUICK: { label: string; to: string; icon: Parameters<typeof Icon>[0]['name'] }[] = [
  { label: 'Order issue', to: '/help/new?category=order', icon: 'bag' },
  { label: 'Payment or refund', to: '/help/new?category=payment', icon: 'card' },
  { label: 'Ride issue', to: '/help/new?category=ride', icon: 'ride' },
  { label: 'Booking issue', to: '/help/new?category=bookings', icon: 'ticket' },
  { label: 'Wallet', to: '/help/new?category=wallet', icon: 'wallet' },
  { label: 'Account & safety', to: '/help/new?category=account', icon: 'shield' },
];
const OPEN = new Set(['open', 'in_progress', 'awaiting_customer', 'reopened']);
export const statusTone = (s: string) => (s === 'resolved' || s === 'closed' ? 'ok' : s === 'awaiting_customer' ? 'pending' : 'info');

/** Help & Support: answers first (searchable articles written from how Click. actually works), then a request that
 *  carries the order or booking it's about. */
export function HelpPage() {
  const { status } = useAuth();
  const home = useQuery({ queryKey: ['help', 'home'], queryFn: api.money.support.home });
  const tickets = useQuery({ queryKey: ['customer', 'support', 'list'], queryFn: () => api.money.support.list(), enabled: status === 'authenticated' });
  const [q, setQ] = useState('');
  const [term, setTerm] = useState('');
  useEffect(() => { const t = setTimeout(() => setTerm(q.trim()), 300); return () => clearTimeout(t); }, [q]);
  const search = useQuery({ queryKey: ['help', 'search', term], queryFn: () => api.money.support.search(term), enabled: term.length >= 2 });
  const [cat, setCat] = useState('');
  const open = tickets.data?.results.filter((t) => OPEN.has(t.status)) ?? [];

  return (
    <div className="mn-page">
      <MoneyHead title="Help & Support" />
      <div className="mn-search mn-search--lg"><Icon name="search" size={20} />
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search help: refund, cancel, OTP, wallet…" aria-label="Search help articles" /></div>
      {term.length >= 2 && (
        <Section title={`Results for “${term}”`} id="mn-help-results">
          {!search.data ? <Skeleton height={100} /> : search.data.results.length === 0 ? (
            <EmptyState icon="help" title="No articles match" message="Try other words, or raise a request below." action={<Link to="/help/new" className="btn btn--primary">Contact support</Link>} />
          ) : <ArticleList rows={search.data.results} />}
        </Section>
      )}

      {open.length > 0 && (
        <Section title="Your open requests" id="mn-open" action={<Link to="/help/tickets" className="mn-link small">All requests</Link>}>
          <ul className="mn-list">{open.slice(0, 3).map((t) => (
            <li key={t.id}><Link to={`/help/tickets/${t.id}`} className="mn-row"><span className="mn-row__icon"><Icon name={iconFor(t.category)} size={18} /></span>
              <span className="mn-row__text"><strong className="truncate">{t.subject}</strong><span className="small mn-muted">{t.reference} · updated {dateOf(t.lastUpdate)}</span></span>
              <Pill tone={statusTone(t.status)}>{t.statusLabel}</Pill></Link></li>
          ))}</ul>
        </Section>
      )}

      <Section title="Get help with" id="mn-quick">
        <div className="mn-quick">{QUICK.map((x) => <Link key={x.label} to={x.to} className="mn-quick__item"><Icon name={x.icon} size={22} /><span>{x.label}</span></Link>)}</div>
      </Section>

      {home.isError ? <ErrorState error={home.error} onRetry={() => home.refetch()} /> : !home.data ? <Skeleton height={240} /> : (
        <>
          <Section title="Popular" id="mn-popular"><ArticleList rows={home.data.popular} /></Section>
          <Section title="Browse by service" id="mn-cats">
            <div className="mn-chips mn-chips--wrap">
              {home.data.categories.filter((c) => c.articles > 0).map((c) => <button key={c.code} type="button" className="mn-chip" aria-pressed={cat === c.code} onClick={() => setCat(cat === c.code ? '' : c.code)}>
                <Icon name={iconFor(c.code)} size={15} />{c.label}</button>)}
            </div>
            {cat && (
              <>
                <ArticleList rows={home.data.articles.filter((a) => a.category === cat)} />
                <Link to={`/help/new?category=${cat}`} className="mn-row mn-row--card"><span className="mn-row__icon"><Icon name="send" size={18} /></span>
                  <span className="mn-row__text"><strong>Still need help?</strong><span className="small mn-muted">Raise a request about {home.data.categories.find((c) => c.code === cat)?.label}</span></span><Icon name="right" size={16} /></Link>
              </>
            )}
          </Section>
          <Section title="Contact Click. Support" id="mn-contact">
            <div className="mn-card mn-contact">
              <Link to="/help/new" className="btn btn--primary">Raise a support request</Link>
              <p className="small mn-muted">Requests are the fastest way to reach us: your order or booking is attached and replies appear in the request.</p>
              <dl className="mn-dl">
                <div><dt>Email</dt><dd><a href={`mailto:${home.data.contact.email}`} className="mn-link">{home.data.contact.email}</a></dd></div>
                <div><dt>Phone</dt><dd>{home.data.contact.phoneCallable ? <a href={`tel:${home.data.contact.phone}`} className="mn-link">{home.data.contact.phone}</a> : home.data.contact.phone}</dd></div>
                {home.data.contact.hours && <div><dt>Hours</dt><dd>{home.data.contact.hours}</dd></div>}
              </dl>
              <p className="small mn-muted">In an emergency during a ride, use the emergency call in the ride’s safety panel, or call 112.</p>
            </div>
          </Section>
        </>
      )}
      {status === 'authenticated' && <Link to="/help/tickets" className="mn-row mn-row--card"><span className="mn-row__icon"><Icon name="history" size={18} /></span>
        <span className="mn-row__text"><strong>My support requests</strong><span className="small mn-muted">{tickets.data ? `${tickets.data.count ?? tickets.data.results.length} total` : 'All your requests and replies'}</span></span><Icon name="right" size={16} /></Link>}
    </div>
  );
}

function ArticleList({ rows }: { rows: { slug: string; title: string; summary: string; category: string }[] }) {
  return (
    <ul className="mn-list">{rows.map((a) => (
      <li key={a.slug}><Link to={`/help/articles/${a.slug}`} className="mn-row"><span className="mn-row__icon"><Icon name={iconFor(a.category)} size={18} /></span>
        <span className="mn-row__text"><strong>{a.title}</strong><span className="small mn-muted">{a.summary}</span></span><Icon name="right" size={16} /></Link></li>
    ))}</ul>
  );
}
