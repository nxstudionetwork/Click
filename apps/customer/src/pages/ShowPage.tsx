import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { useAuth } from '../auth/AuthProvider';
import { EmptyState, ErrorState, Icon, Skeleton, useToast } from '../components/ui';
import { useThemeOverride } from '../components/layout/AppShell';
import { dayOf, timeOf } from '../features/showtime/parts';
import { api } from '../lib/api';
import { formatMoney } from '../lib/format';

/**
 * Seat selection on the screen's real layout. Availability refreshes every 15 seconds and on every hold attempt;
 * the server decides (seats taken in the meantime are reported and unselected). Continuing holds the seats for a
 * few minutes while the customer checks out.
 */
export function ShowPage() {
  useThemeOverride('movies');
  const { id = '' } = useParams();
  const { status } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const map = useQuery({ queryKey: ['showtime', 'seats', id], queryFn: () => api.events.seatMap(id), refetchInterval: 15_000 });
  const [picked, setPicked] = useState<string[]>([]);
  const m = map.data;
  const price = useMemo(() => Object.fromEntries((m?.tiers ?? []).map((t) => [t.code, Number(t.price)])), [m]);
  const tierOf = useMemo(() => Object.fromEntries((m?.rows ?? []).flatMap((r) => r.seats.map((s) => [s.label, r.tier]))), [m]);
  // Drop seats that became unavailable on a refresh.
  useEffect(() => {
    if (!m) return;
    const open = new Set(m.rows.flatMap((r) => r.seats.filter((s) => s.state === 'available' || s.state === 'mine').map((s) => s.label)));
    setPicked((p) => p.filter((l) => open.has(l)));
  }, [m]);
  const hold = useMutation({
    mutationFn: () => api.showtime.hold(id, picked),
    onSuccess: (h) => navigate(`/showtime/checkout/${h.id}`),
    onError: (e) => {
      toast(e instanceof ApiError ? e.message : 'Couldn’t hold those seats. Try again.', 'error');
      map.refetch();
    },
  });

  if (map.isError) {
    return map.error instanceof ApiError && map.error.status === 404
      ? <div className="st-page"><EmptyState icon="ticket" title="This showtime isn’t available" message="It may have started or been cancelled." action={<Link className="btn btn--primary" to="/showtime">See what’s playing</Link>} /></div>
      : <div className="st-page"><ErrorState error={map.error} onRetry={() => map.refetch()} /></div>;
  }
  if (map.isPending || !m) return <div className="st-page"><Skeleton height={60} radius={14} /><Skeleton height={360} radius={18} /></div>;

  const total = picked.reduce((sum, l) => sum + (price[tierOf[l]!] ?? 0), 0);
  const toggle = (label: string) => setPicked((p) => p.includes(label) ? p.filter((x) => x !== label) : p.length >= m.maxPerBooking ? p : [...p, label]);
  let lastTier = '';

  return (
    <div className="st-page st-seats" data-theme="movies">
      <Link to={`/showtime/${m.event.slug}#times`} className="btn btn--ghost btn--sm" style={{ alignSelf: 'flex-start', paddingLeft: 4, color: 'var(--c-ink-2)' }}><Icon name="back" size={18} /> {m.event.title}</Link>
      <header className="stack" style={{ gap: 4 }}>
        <h1 style={{ fontSize: 'clamp(1.3rem, 4vw, 1.8rem)' }}>{m.event.title}</h1>
        <span className="small muted">{m.venue.name} · {m.screen} · {dayOf(m.startsAt)}, {timeOf(m.startsAt)}</span>
        <span className="small" style={{ color: 'var(--c-ink-2)' }}>{[m.language, m.format, m.sound].filter(Boolean).join(' • ')}</span>
      </header>
      {m.myHold && (
        <div className="st-box" role="status"><strong>You already have seats held: {m.myHold.seats.join(', ')}</strong>
          <div className="row"><Link to={`/showtime/checkout/${m.myHold.id}`} className="btn btn--primary btn--sm">Continue to checkout</Link>
            <span className="small muted">Choosing new seats replaces that hold.</span></div></div>
      )}
      <div className="st-legend" aria-label="Seat legend">
        <span><i /> Available</span><span><i className="sel" /> Selected</span><span><i className="taken" /> Taken</span><span><i className="acc" /> Accessible</span>
      </div>
      <div className="st-hall">
        <div className="st-hall__inner" role="group" aria-label="Seats (front row nearest the screen)">
          <div className="st-screen" aria-hidden="true">SCREEN</div>
          {m.rows.map((r) => {
            const tier = m.tiers.find((t) => t.code === r.tier);
            const header = r.tier !== lastTier && tier ? <div key={`t-${r.row}`} className="st-tier-label">{tier.name} · {formatMoney(tier.price, m.currency)}</div> : null;
            lastTier = r.tier;
            return [header, (
              <div key={r.row} className="st-row">
                <span className="st-row__label" aria-hidden="true">{r.row}</span>
                {r.seats.map((s) => {
                  const selectable = s.state === 'available' || s.state === 'mine';
                  const on = picked.includes(s.label);
                  return [
                    <button key={s.label} type="button" disabled={!selectable} aria-pressed={on}
                      className={`st-seat st-seat--${s.state === 'mine' ? 'available' : s.state} ${s.accessible ? 'st-seat--accessible' : ''} ${r.tier === 'recliner' ? 'st-seat--recliner' : ''}`}
                      aria-label={`Seat ${s.label}, ${tier?.name ?? r.tier}${s.accessible ? ', accessible' : ''}, ${s.state === 'available' || s.state === 'mine' ? (on ? 'selected' : 'available') : s.state === 'unavailable' ? 'not available' : 'taken'}`}
                      onClick={() => toggle(s.label)}>{s.state === 'booked' || s.state === 'held' ? '' : s.number}</button>,
                    r.gaps.includes(s.number) ? <span key={`g-${s.label}`} className="st-aisle" aria-hidden="true" /> : null,
                  ];
                })}
                <span className="st-row__label" aria-hidden="true">{r.row}</span>
              </div>
            )];
          })}
        </div>
      </div>
      <p className="small muted" style={{ textAlign: 'center' }}>Up to {m.maxPerBooking} seats. Seats are held for {m.holdMinutes} minutes while you check out.</p>

      <div className="st-bar" role="region" aria-label="Selection">
        <div className="st-bar__info">
          <strong>{picked.length ? formatMoney(total, m.currency) : 'Choose seats'}</strong>
          <span>{picked.length ? `${picked.length} seat${picked.length > 1 ? 's' : ''}: ${picked.join(', ')}` : 'Tap seats on the map'}</span>
        </div>
        <button type="button" className="st-btn st-btn--book" disabled={!picked.length || hold.isPending}
          onClick={() => (status === 'authenticated' ? hold.mutate() : navigate(`/login?next=${encodeURIComponent(location.pathname)}`))}>
          {hold.isPending ? 'Holding…' : 'Continue'}
        </button>
      </div>
    </div>
  );
}
