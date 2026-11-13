import { Link, Navigate } from 'react-router-dom';
import { Button, Icon, Skeleton } from '@click/ui';
import type { PartnerHome, PartnerStatus } from '@click/api';
import { AppShell } from '../components/AppShell';
import { Photo } from '../components/Photo';
import { visualFor } from '../config/visuals';
import { LocationShare } from '../features/home/LocationShare';
import { useHome } from '../features/home/queries';
import {
  Activity, AvailabilityCard, EarningsCard, Empty, listSkeleton, Module, Overview, Performance, QuickActions, SectionBody, WorkList,
} from '../features/home/sections';
import { apiMessage, greeting } from '../lib/format';
import { usePartnerSession } from '../session/PartnerSession';

const STATUS_COPY: Partial<Record<PartnerStatus, string>> = {
  verification_pending: 'Click is reviewing your profile. You can start receiving work once you’re verified.',
  rejected: 'Your verification wasn’t approved. Contact Click Partner support with your Partner ID to resolve it.',
  suspended: 'Your Partner account is suspended. Contact Click Partner support with your Partner ID.',
  inactive: 'Your Partner account is inactive.',
};

const NOUN_EMPTY: Record<string, { title: string; message: string }> = {
  ride: { title: 'You’re all caught up.', message: 'No ride requests right now.' },
  order: { title: 'You’re all caught up.', message: 'No new orders right now.' },
  booking: { title: 'You’re all caught up.', message: 'No shows starting in the next two hours.' },
};

const ACTIVE_TITLE: Record<string, string> = { ride: 'Active trip', order: 'In progress', booking: 'Now showing' };

function Hero({ home, loading }: { home?: PartnerHome; loading: boolean }) {
  const { partner: s } = usePartnerSession();
  const partner = s.state!.partner!;
  const scene = visualFor(partner.partnerType.slug).scenes[0]!;
  return (
    <section className="hero" aria-labelledby="hello">
      <div className="hero__media" aria-hidden="true">
        <Photo photo={scene.photo} alt="" sizes="(min-width: 960px) 760px, 100vw" eager />
      </div>
      <div className="hero__content">
        <p className="hero__eyebrow">{partner.category.name} workspace</p>
        <h1 id="hello">{greeting()}{home ? `, ${home.greetingName}` : ''}</h1>
        {loading ? <Skeleton width="70%" height={18} /> : <p className="hero__context">{home?.context}</p>}
      </div>
    </section>
  );
}

export function HomePage() {
  const { partner: state } = usePartnerSession();
  const partner = state.state?.partner;
  const home = useHome();
  if (!partner?.partnerCode) return <Navigate to="/" replace />;
  const data = home.data;
  const loading = home.isPending;
  const noun = data?.workspace.workNoun ?? 'work';
  const hasActive = data?.active.status === 'ok' && data.active.data.length > 0;
  const incoming = data?.incoming.status === 'ok' ? data.incoming.data : [];
  const live = data?.workspace.state === 'live';

  return (
    <AppShell>
      <div className="dash">
        {home.isError && !data ? (
          <div className="dash__error" role="alert">
            <Icon name="alert" size={28} />
            <h2>Couldn’t load your dashboard</h2>
            <p className="muted">{apiMessage(home.error)}</p>
            <Button onClick={() => void home.refetch()}>Try again</Button>
          </div>
        ) : (
          <>
            <div className="dash__main">
              <Hero home={data} loading={loading} />
              {STATUS_COPY[partner.status] && (
                <div className="notice notice--warning" role="status"><Icon name="clock" size={18} /><span>{STATUS_COPY[partner.status]}</span></div>
              )}
              {home.isError && data && (
                <div className="notice notice--warning" role="status"><Icon name="alert" size={18} /><span>Can’t refresh right now. Showing what Click last sent ({new Date(data.generatedAt).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' })}).</span></div>
              )}
              {loading ? <Skeleton height={92} radius={20} /> : data && <AvailabilityCard home={data} />}
              {data && <LocationShare home={data} />}

              {!loading && data && !live && (
                <section className="upcoming" aria-labelledby="up-h">
                  <span className="upcoming__icon" aria-hidden="true"><Icon name={data.workspace.state === 'upcoming' ? 'sparkle' : 'store'} size={24} /></span>
                  <div>
                    <h2 id="up-h">{data.workspace.state === 'upcoming' ? 'Coming to Click' : 'Almost ready'}</h2>
                    <p>{data.workspace.message}</p>
                    <Link to="/card" className="text-btn">View your Partner card <Icon name="right" size={14} /></Link>
                  </div>
                </section>
              )}

              {(loading || hasActive) && (
                <Module id="active-h" title={ACTIVE_TITLE[noun] ?? 'Active work'} icon="clock" className="mod--active">
                  <SectionBody section={data?.active} loading={loading} skeleton={listSkeleton}>
                    {(items) => <WorkList items={items} emphasis />}
                  </SectionBody>
                </Module>
              )}

              {(loading || live) && (
                <Module id="action-h" title="Action required" icon="bell" className="mod--action"
                  action={live ? <Link to="/work" className="text-btn">View all <Icon name="right" size={14} /></Link> : undefined}>
                  <SectionBody section={data?.actionRequired} loading={loading} skeleton={listSkeleton}
                    empty={(items) => (items.length ? null : (
                      <Empty icon="check" title={NOUN_EMPTY[noun]?.title ?? 'You’re all caught up.'}
                        message={data?.availability.isOn || !data?.availability.canChange ? NOUN_EMPTY[noun]?.message ?? 'Nothing needs your attention.'
                          : `${NOUN_EMPTY[noun]?.message ?? ''} ${data.availability.turnOn} to start receiving work.`.trim()} />
                    ))}>
                    {(items) => <WorkList items={items} />}
                  </SectionBody>
                </Module>
              )}

              {data && <QuickActions home={data} />}

              {incoming.length > 0 && (
                <Module id="incoming-h" title="Later today" icon="history">
                  <WorkList items={incoming} />
                </Module>
              )}

              {(loading || live) && <Overview home={data} loading={loading} />}
            </div>

            {(loading || live) && (
              <aside className="dash__side" aria-label="Earnings and performance">
                <EarningsCard home={data} loading={loading} />
                <Performance home={data} loading={loading} />
                <Activity home={data} loading={loading} />
              </aside>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}
