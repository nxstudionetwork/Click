import { useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button, EmptyState, ErrorState, Icon, Skeleton, useToast } from '../components/ui';
import { MoneyHead, Pill, Section, dateOf } from '../features/money/parts';
import { useT } from '../i18n';
import { track } from '../lib/analytics';
import { api } from '../lib/api';

export const REFERRAL_KEY = 'click.referral';

/** Refer a friend: your code and link, how rewards work (from the backend's rules), and who joined. */
export function ReferralsPage() {
  const t = useT();
  const toast = useToast();
  const q = useQuery({ queryKey: ['referrals'], queryFn: api.money.referrals.mine });
  if (q.isError) return <div className="mn-page"><MoneyHead title={t('refer.title')} /><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  if (!q.data) return <div className="mn-page"><MoneyHead title={t('refer.title')} /><Skeleton height={300} /></div>;
  const d = q.data;
  const link = `${window.location.origin}${d.link}`;
  const share = async () => {
    const text = `Join me on Click. — use my invite code ${d.code}: ${link}`;
    try {
      if (navigator.share) { await navigator.share({ title: 'Click.', text, url: link }); track('referral_shared', { channel: 'share' }); }
      else { await navigator.clipboard.writeText(text); toast(t('refer.copied')); track('referral_shared', { channel: 'copy' }); }
    } catch { /* cancelled */ }
  };
  return (
    <div className="mn-page">
      <MoneyHead title={t('refer.title')} />
      <section className="rf-hero">
        <h2>{t('refer.lead')}</h2>
        <p>{t('refer.reward', { referrer: d.rules.referrerPoints, referee: d.rules.refereePoints })}</p>
        <div className="rf-code"><span className="mn-mono">{d.code}</span>
          <button type="button" className="mn-link small" onClick={async () => { try { await navigator.clipboard.writeText(d.code); toast(t('refer.copied')); } catch { /* ignore */ } }}>
            <Icon name="copy" size={14} /> {t('refer.copy')}</button></div>
        <Button onClick={share}><Icon name="share" size={16} /> {t('refer.share')}</Button>
      </section>
      <Section title={t('refer.how')} id="rf-how">
        <ul className="mn-bullets small">
          <li>{d.rules.how}</li>
          <li>Rewards are Click. points, given once per new customer, up to {d.rules.monthlyCap} rewarded invites a month.</li>
          <li>Your friend must be new to Click. and use your code when creating their account.</li>
        </ul>
      </Section>
      <Section title={t('refer.yours')} id="rf-list">
        {d.referrals.length === 0 ? <EmptyState icon="gift" title={t('refer.none')} /> : (
          <ul className="mn-list">{d.referrals.map((r) => (
            <li key={r.id} className="mn-row mn-row--static"><span className="mn-row__icon"><Icon name="user" size={18} /></span>
              <span className="mn-row__text"><strong>{r.name}</strong><span className="small mn-muted">Joined {dateOf(r.joinedAt)}{r.reason ? ` · ${r.reason}` : ''}</span></span>
              <Pill tone={r.status === 'rewarded' ? 'ok' : r.status === 'joined' ? 'pending' : 'info'}>{r.statusLabel}</Pill></li>
          ))}</ul>
        )}
        {d.earnedPoints > 0 && <p className="small">You’ve earned {d.earnedPoints.toLocaleString('en-IN')} points from invites. <Link to="/rewards" className="mn-link">Rewards</Link></p>}
      </Section>
    </div>
  );
}

/** /join/:code — an invite link. Keeps the code for sign-up, then goes to sign in. */
export function JoinPage() {
  const { code = '' } = useParams();
  const q = useQuery({ queryKey: ['referral', code], queryFn: () => api.money.referrals.check(code), retry: false });
  useEffect(() => { if (q.data) { try { sessionStorage.setItem(REFERRAL_KEY, q.data.code); } catch { /* ignore */ } } }, [q.data]);
  if (q.isPending) return <div className="mn-page"><Skeleton height={200} /></div>;
  if (q.isError) return <div className="mn-page"><EmptyState icon="gift" title="This invite link isn’t valid" message="You can still join Click." action={<Link to="/login" className="btn btn--primary">Continue</Link>} /></div>;
  return (
    <div className="mn-page">
      <section className="rf-hero">
        <h2>{q.data.inviter} invited you to Click.</h2>
        <p>Create your account and get {q.data.refereePoints} Click. points when your first order is delivered.</p>
        <Link to="/login" className="btn btn--primary">Get started</Link>
      </section>
    </div>
  );
}

export function readReferral(): string {
  try { return sessionStorage.getItem(REFERRAL_KEY) ?? ''; } catch { return ''; }
}

