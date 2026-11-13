import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, ErrorState, Icon, Skeleton, useConfirm, useToast } from '../components/ui';
import { MoneyHead, Pill, dateOf } from '../features/money/parts';
import { api } from '../lib/api';

const report = (category: string, related?: string, issue?: string) =>
  `/help/new?safety=1&category=${category}${related ? `&related=${related}` : ''}${issue ? `&issue=${encodeURIComponent(issue)}` : ''}`;

function Row({ to, icon, title, sub, tone }: { to: string; icon: Parameters<typeof Icon>[0]['name']; title: string; sub?: string; tone?: 'red' | 'amber' | 'cyan' }) {
  return (
    <Link to={to} className={`sf-row ${tone ? `sf-row--${tone}` : ''}`}>
      <span className="sf-row__icon"><Icon name={icon} size={18} /></span>
      <span className="sf-row__text"><strong>{title}</strong>{sub && <span className="small">{sub}</span>}</span>
      <Icon name="right" size={16} />
    </Link>
  );
}

/** Safety Center: actions that really work for what's happening now (an active ride, a parcel on the way, a professional
 *  coming), reports that become prioritised support requests, and account protection. No invented phone numbers. */
export function SafetyPage() {
  const q = useQuery({ queryKey: ['safety'], queryFn: api.money.safety.get });
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const signOut = useMutation({
    mutationFn: api.money.safety.signOutOthers,
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ['safety'] }); toast(r.signedOut ? `Signed out of ${r.signedOut} other sign-in${r.signedOut > 1 ? 's' : ''}` : 'No other sign-ins'); },
  });
  if (q.isError) return <div className="mn-page sf-page"><MoneyHead title="Safety Center" /><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!q.data) return <div className="mn-page sf-page"><MoneyHead title="Safety Center" /><Skeleton height={380} /></div>;
  const s = q.data;
  const a = s.active;
  return (
    <div className="mn-page sf-page">
      <MoneyHead title="Safety Center" />
      <section className="sf-hero"><Icon name="shield" size={28} /><div><h2>Your safety comes first.</h2><p>Get help fast, report a problem, and keep your account protected.</p></div></section>

      <section className="sf-sec sf-sec--emergency" aria-labelledby="sf-em">
        <h2 id="sf-em">Emergency help</h2>
        <a href={`tel:${s.emergencyNumber}`} className="sf-row sf-row--red"><span className="sf-row__icon"><Icon name="phone" size={18} /></span>
          <span className="sf-row__text"><strong>Call emergency services ({s.emergencyNumber})</strong><span className="small">Police, ambulance and fire, all over India</span></span><Icon name="right" size={16} /></a>
        <Row to={report('other', undefined, 'Safety concern')} icon="alert" title="Report an urgent safety issue" sub="Goes to Click. Support as an urgent case" tone="amber" />
        <Row to="/help/new?safety=1" icon="help" title="Contact Click. Support" sub={`${s.support.email}${s.support.phone ? ` · ${s.support.phone}` : ''}`} tone="cyan" />
      </section>

      <section className="sf-sec" aria-labelledby="sf-ride">
        <h2 id="sf-ride">Ride safety</h2>
        {a.rides.map((r) => (
          <div key={r.id} className="sf-live"><Pill tone="pending">{r.status}</Pill><strong>{r.title}</strong>{r.driver && <span className="small">Driver: {r.driver}</span>}
            <div className="mn-row2"><Link to={r.link} className="btn btn--sm btn--primary">Open trip · share &amp; SOS</Link>
              <Link to={report('ride', `ride:${r.id}`, 'Safety concern')} className="btn btn--sm btn--outline">Report</Link></div></div>
        ))}
        <Row to={report('ride', undefined, 'Unsafe driving')} icon="ride" title="Report a driver or unsafe driving" />
        <Row to={report('ride', undefined, 'Driver or vehicle didn’t match')} icon="car" title="Driver or vehicle didn’t match the app" />
        <Row to={report('ride', undefined, 'Lost item')} icon="bag" title="I left something in a ride" />
        <p className="small sf-tip">During a ride, the trip screen has share-trip and emergency call. Always check the vehicle number and driver photo before you get in.</p>
      </section>

      <section className="sf-sec" aria-labelledby="sf-parcel">
        <h2 id="sf-parcel">Parcel safety</h2>
        {a.parcels.map((p) => <Row key={p.id} to={p.link} icon="parcel" title={p.title} sub={`${p.number} · ${p.status} · PIN-verified handover`} />)}
        <Row to={report('parcel', undefined, 'Suspicious delivery')} icon="alert" title="Report a suspicious delivery" />
        <Row to={report('parcel', undefined, 'Damaged parcel')} icon="parcel" title="Report a damaged package" />
        <Row to={report('parcel', undefined, 'Unsafe delivery behaviour')} icon="user" title="Report unsafe delivery behaviour" />
        <Row to="/help/articles/parcel-tracking" icon="book" title="What you can’t send, and how handover PINs work" />
      </section>

      <section className="sf-sec" aria-labelledby="sf-svc">
        <h2 id="sf-svc">Services safety</h2>
        {a.services.map((b) => (
          <div key={b.id} className="sf-live"><Pill tone="info">{b.status}</Pill><strong>{b.title}{b.professional ? ` · ${b.professional}` : ''}</strong>
            {b.professional && <span className="small">{b.verified ? 'Verified Click. partner' : 'Verification pending'}{b.rating ? ` · ★ ${b.rating}` : ''}{b.jobs ? ` · ${b.jobs} jobs` : ''}</span>}
            <div className="mn-row2"><Link to={b.link} className="btn btn--sm btn--outline">Booking</Link><Link to={report('service', `service_booking:${b.id}`, 'Unsafe behaviour')} className="btn btn--sm btn--outline">Report</Link></div></div>
        ))}
        <Row to={report('service', undefined, 'Inappropriate conduct')} icon="user" title="Report inappropriate conduct" />
        <Row to={report('service', undefined, 'Professional didn’t match the profile')} icon="shield" title="The professional didn’t match their profile" />
        <p className="small sf-tip">Match the professional’s name and photo with your booking before letting them in. You can cancel for safety reasons from the booking.</p>
      </section>

      <section className="sf-sec" aria-labelledby="sf-pay">
        <h2 id="sf-pay">Payments &amp; account safety</h2>
        <Row to={report('payment', undefined, 'Unauthorised payment')} icon="card" title="Report an unauthorised payment" tone="amber" />
        <Row to={report('wallet', undefined, 'Transaction I don’t recognise')} icon="wallet" title="A wallet transaction I don’t recognise" />
        <div className="sf-live"><strong>{s.sessions.active} active sign-in{s.sessions.active === 1 ? '' : 's'}</strong>
          <span className="small">Signed in somewhere you don’t recognise? Sign out everywhere else.</span>
          <Button size="sm" variant="secondary" loading={signOut.isPending} onClick={async () => { if (await confirm({ title: 'Sign out of other devices?', message: 'You stay signed in here.', confirmLabel: 'Sign out others' })) signOut.mutate(); }}>Sign out other devices</Button></div>
        <ul className="mn-bullets small sf-tips"><li>Click. never asks for your OTP, UPI PIN, card number or password — not even Support.</li>
          <li>Links asking you to “verify” your account outside the app aren’t from Click.</li><li>Your card details are never stored by Click.</li></ul>
      </section>

      <section className="sf-sec" aria-labelledby="sf-trip">
        <h2 id="sf-trip">Travel, stays &amp; bookings</h2>
        {[...a.trips, ...a.stays].map((t) => <Row key={t.id} to={t.link} icon="pin" title={t.title} sub={t.status} />)}
        <Row to={report('travel', undefined, 'Safety concern')} icon="bus" title="Report a travel safety issue" />
        <Row to={report('hotels', undefined, 'Suspicious listing')} icon="hotel" title="Report a suspicious stay or listing" />
        <Row to={report('bookings', undefined, 'Suspicious provider')} icon="temple" title="Report a suspicious provider" />
      </section>

      <section className="sf-sec" aria-labelledby="sf-rep">
        <h2 id="sf-rep">Your safety reports</h2>
        {s.reports.length === 0 ? <p className="small">No safety reports. Anything you report here reaches Click. Support as a priority case.</p> : s.reports.map((r) => (
          <Row key={r.id} to={`/help/tickets/${r.id}`} icon="shield" title={r.subject} sub={`${r.reference} · ${r.statusLabel} · ${dateOf(r.createdAt)}`} tone={r.priority === 'urgent' ? 'red' : undefined} />
        ))}
        <Row to="/help/new?safety=1" icon="send" title="Report a problem" tone="cyan" />
      </section>
    </div>
  );
}
