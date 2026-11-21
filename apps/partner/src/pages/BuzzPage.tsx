import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Button, Icon, Skeleton, useToast } from '@click/ui';
import type { BuzzPostAction, BuzzPostStatus, PartnerBuzzOverview, PartnerBuzzPost } from '@click/api';
import { AppShell } from '../components/AppShell';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { BuzzComposer } from '../features/buzz/BuzzComposer';
import { useBuzzCommunity, useBuzzOverview, useCommunityLike, usePostAction, useReportPost } from '../features/buzz/queries';
import { Empty } from '../features/home/sections';
import { apiMessage } from '../lib/format';
import { formatMoney } from '../lib/money';

const TONE: Record<BuzzPostStatus, string> = { live: 'success', scheduled: 'info', in_review: 'info', draft: 'muted', paused: 'muted',
  expired: 'muted', archived: 'muted', rejected: 'urgent', removed: 'urgent' };
const FILTERS: { key: '' | BuzzPostStatus; label: string }[] = [
  { key: '', label: 'All' }, { key: 'live', label: 'Live' }, { key: 'scheduled', label: 'Scheduled' }, { key: 'in_review', label: 'In review' },
  { key: 'draft', label: 'Drafts' }, { key: 'paused', label: 'Paused' }, { key: 'rejected', label: 'Not approved' }, { key: 'expired', label: 'Expired' },
  { key: 'archived', label: 'Archived' },
];
const ACTION_LABEL: Record<Exclude<BuzzPostAction, 'edit'>, string> = { submit: 'Send for review', withdraw: 'Withdraw', pause: 'Pause',
  resume: 'Resume', archive: 'Archive', restore: 'Restore to drafts', delete: 'Delete' };
const ACTION_DONE: Record<Exclude<BuzzPostAction, 'edit'>, string> = { submit: 'Sent to Click for review', withdraw: 'Moved back to drafts',
  pause: 'Post paused', resume: 'Post resumed', archive: 'Post archived', restore: 'Restored to drafts', delete: 'Post deleted' };

const day = (iso: string) => new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' });

function when(p: PartnerBuzzPost) {
  if (p.status === 'scheduled' && p.publishAt) return `Starts ${day(p.publishAt)}`;
  if (p.status === 'expired' && p.expiresAt) return `Ended ${day(p.expiresAt)}`;
  if (p.expiresAt) return `${p.status === 'live' ? 'Live until' : 'Runs until'} ${day(p.expiresAt)}`;
  return '';
}

function PostCard({ post, onEdit }: { post: PartnerBuzzPost; onEdit: () => void }) {
  const act = usePostAction();
  const toast = useToast();
  const [confirm, setConfirm] = useState<'delete' | 'archive' | null>(null);
  const cover = post.media[0];
  const run = (action: Exclude<BuzzPostAction, 'edit'>) => act.mutate({ id: post.id, action }, {
    onSuccess: () => { toast(ACTION_DONE[action]); setConfirm(null); },
    onError: (e) => toast(apiMessage(e), 'error'),
  });
  const s = post.stats;

  return (
    <li className={`work work--${TONE[post.status]} bpost`}>
      <div className="bpost__row">
        <span className="bpost__thumb" aria-hidden="true">
          {cover?.kind === 'video' ? <><video src={cover.url} muted preload="metadata" /><span className="buzzc__badge"><Icon name="play" size={12} /></span></>
            : cover ? <img src={cover.thumb || cover.url} alt="" loading="lazy" /> : <Icon name="sparkle" size={24} />}
        </span>
        <div className="bpost__main">
          <div className="bpost__top">
            <span className={`tag tag--${TONE[post.status]}`}>{post.statusLabel}</span>
            <span className="small muted">{post.kindLabel}{post.audience === 'partners' ? ' · Partners only' : ''}</span>
          </div>
          <h3>{post.headline}</h3>
          {post.caption && <p className="small muted bpost__caption">{post.caption}</p>}
          <p className="small">
            {post.ctaLabel ? <><strong>{post.ctaLabel}</strong> → {post.targetTitle}</> : 'No button'}
            {post.product && <> · {post.product.name} {formatMoney(post.product.price)}{!post.product.available && <span className="tone-danger"> (unavailable now)</span>}</>}
            {post.offer && <> · Offer: {post.offer.title}</>}
          </p>
          {when(post) && <p className="small muted">{when(post)}</p>}
        </div>
      </div>
      {post.reviewNote && <p className="ticket__instr"><Icon name="alert" size={16} /> Click: {post.reviewNote}</p>}
      {post.status === 'in_review' && <p className="small muted">Click usually reviews posts within a day. You’ll get a notification.</p>}
      {['live', 'paused', 'expired', 'archived', 'scheduled'].includes(post.status) && (
        <dl className="bstats" aria-label="Performance">
          <div><dt>Views</dt><dd>{s.views.toLocaleString('en-IN')}</dd></div>
          <div><dt>Button taps</dt><dd>{s.ctaClicks.toLocaleString('en-IN')}</dd></div>
          <div><dt>Tap rate</dt><dd>{s.ctr === null ? '—' : `${s.ctr}%`}</dd></div>
          <div><dt>Likes</dt><dd>{s.likes}</dd></div>
          <div><dt>Saves</dt><dd>{s.saves}</dd></div>
          {s.openReports > 0 && <div><dt>Reports</dt><dd className="tone-danger">{s.openReports}</dd></div>}
        </dl>
      )}
      <div className="work__actions">
        {post.actions.includes('edit') && <Button size="sm" variant="outline" onClick={onEdit}><Icon name="edit" size={14} /> Edit</Button>}
        {post.actions.filter((a): a is Exclude<BuzzPostAction, 'edit'> => a !== 'edit').map((a) => (
          <Button key={a} size="sm" variant={a === 'delete' ? 'ghost' : a === 'submit' ? 'primary' : 'outline'}
            loading={act.isPending && act.variables?.action === a}
            onClick={() => (a === 'delete' || a === 'archive' ? setConfirm(a) : run(a))}>{ACTION_LABEL[a]}</Button>
        ))}
      </div>
      <ConfirmDialog open={confirm !== null} title={confirm === 'delete' ? 'Delete this post?' : 'Archive this post?'}
        message={confirm === 'delete' ? 'The post, its photos and videos are deleted for good. Its numbers are lost too.'
          : 'It comes off Buzz now. You can restore it to drafts later.'}
        confirmLabel={confirm === 'delete' ? 'Delete' : 'Archive'} tone={confirm === 'delete' ? 'danger' : 'primary'}
        pending={act.isPending} error={act.error ? apiMessage(act.error) : null}
        onConfirm={() => confirm && run(confirm)} onClose={() => setConfirm(null)} />
    </li>
  );
}

function MyPosts({ data }: { data: PartnerBuzzOverview }) {
  const [filter, setFilter] = useState<'' | BuzzPostStatus>('');
  const [editing, setEditing] = useState<PartnerBuzzPost | 'new' | null>(null);
  const posts = data.posts.filter((p) => !filter || p.status === filter);
  const total = data.posts.length;
  const count = (s: BuzzPostStatus) => data.counts.find((c) => c.status === s)?.count ?? 0;

  if (editing) return <BuzzComposer data={data} post={editing === 'new' ? undefined : editing} onDone={() => setEditing(null)} />;
  return (
    <>
      {data.listings.length === 0 ? (
        <Empty icon="sparkle" title="Buzz opens once you have a live listing."
          message="Posts always lead customers to something they can order or book on Click. When your listing is live, you can post here." />
      ) : (
        <div className="spread buzz-head">
          <dl className="bstats bstats--hero" aria-label="Last 7 days">
            <div><dt>Views (7 days)</dt><dd>{data.totals.views7d.toLocaleString('en-IN')}</dd></div>
            <div><dt>Button taps (7 days)</dt><dd>{data.totals.clicks7d.toLocaleString('en-IN')}</dd></div>
            <div><dt>Likes</dt><dd>{data.totals.likes}</dd></div>
            <div><dt>Saves</dt><dd>{data.totals.saves}</dd></div>
          </dl>
          <Button onClick={() => setEditing('new')}><Icon name="plus" size={16} /> Create post</Button>
        </div>
      )}
      {total > 0 && (
        <div className="seg seg--wrap" role="group" aria-label="Filter posts">
          {FILTERS.filter((f) => !f.key || count(f.key)).map((f) => (
            <button key={f.key} type="button" className={`seg__btn ${filter === f.key ? 'is-active' : ''}`} aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}>
              {f.label} · {f.key ? count(f.key) : total}</button>
          ))}
        </div>
      )}
      {total === 0 && data.listings.length > 0 ? (
        <Empty icon="sparkle" title="No posts yet."
          message="Share something new: a dish, a deal, an update. Add a photo or short video and a button that leads to your listing on Click." />
      ) : (
        <ul className="work-list">{posts.map((p) => <PostCard key={p.id} post={p} onEdit={() => setEditing(p)} />)}</ul>
      )}
    </>
  );
}

function Community() {
  const feed = useBuzzCommunity(true);
  const like = useCommunityLike();
  const report = useReportPost();
  const toast = useToast();
  const [reporting, setReporting] = useState<string | null>(null);
  if (feed.isPending) return <Skeleton height={160} radius={20} />;
  if (feed.isError) return <div className="dash__error" role="alert"><p className="muted">{apiMessage(feed.error)}</p><Button onClick={() => void feed.refetch()}>Try again</Button></div>;
  if (feed.data.results.length === 0) return <Empty icon="team" title="Nothing from fellow partners yet." message="Approved posts from other Click partners show up here." />;
  return (
    <>
      <ul className="work-list">
        {feed.data.results.map((p) => {
          const cover = p.media[0];
          return (
            <li key={p.id} className="work bpost">
              <div className="bpost__row">
                <span className="bpost__thumb" aria-hidden="true">
                  {cover?.kind === 'video' ? <video src={cover.url} muted preload="metadata" /> : cover ? <img src={cover.thumb || cover.url} alt="" loading="lazy" /> : <Icon name="sparkle" size={24} />}
                </span>
                <div className="bpost__main">
                  <p className="small muted"><strong>{p.partner}</strong> · {p.category} · {p.kindLabel}{p.audience === 'partners' ? ' · Partners only' : ''}</p>
                  <h3>{p.headline}</h3>
                  {p.caption && <p className="small bpost__caption">{p.caption}</p>}
                </div>
              </div>
              <div className="work__actions">
                <Button size="sm" variant={p.liked ? 'primary' : 'outline'} aria-pressed={p.liked} loading={like.isPending && like.variables === p.id}
                  onClick={() => like.mutate(p.id, { onError: (e) => toast(apiMessage(e), 'error') })}><Icon name="heart" size={14} /> {p.likes}</Button>
                <Button size="sm" variant="ghost" onClick={() => setReporting(p.id)}>Report</Button>
              </div>
            </li>
          );
        })}
      </ul>
      <ConfirmDialog open={reporting !== null} title="Report this post?" message="Tell Click what’s wrong. Moderators review every report."
        confirmLabel="Report" tone="danger" needsReason reasonLabel="What’s wrong?" reasonError="Describe the problem in a few words."
        pending={report.isPending} error={report.error ? apiMessage(report.error) : null} onClose={() => setReporting(null)}
        onConfirm={(note) => reporting && report.mutate({ id: reporting, reason: 'other', note }, {
          onSuccess: () => { toast('Thanks. Click will review it.'); setReporting(null); },
        })} />
    </>
  );
}

/** Click. Buzz for partners: promote what you offer with photos and short videos that lead to your listing on Click. */
export function BuzzPage() {
  const overview = useBuzzOverview();
  const [params, setParams] = useSearchParams();
  const tab = params.get('view') === 'community' ? 'community' : 'mine';
  return (
    <AppShell>
      <div className="page page--wide">
        <div className="page__head">
          <h1>Buzz</h1>
          <p className="muted small">Promote what you offer on Click. Every post leads customers to your listing, and Click reviews it first.</p>
        </div>
        <div className="seg" role="tablist" aria-label="Buzz">
          <button type="button" role="tab" aria-selected={tab === 'mine'} className={`seg__btn ${tab === 'mine' ? 'is-active' : ''}`} onClick={() => setParams({})}>My posts</button>
          <button type="button" role="tab" aria-selected={tab === 'community'} className={`seg__btn ${tab === 'community' ? 'is-active' : ''}`} onClick={() => setParams({ view: 'community' })}>Partner community</button>
        </div>
        {tab === 'community' ? <Community /> : overview.isPending ? <Skeleton height={200} radius={20} /> : overview.isError ? (
          <div className="dash__error" role="alert"><h2>Couldn’t load Buzz</h2><p className="muted">{apiMessage(overview.error)}</p>
            <Button onClick={() => void overview.refetch()}>Try again</Button></div>
        ) : <MyPosts data={overview.data} />}
      </div>
    </AppShell>
  );
}
