import { useMemo, useRef, useState } from 'react';
import { Button, Icon, useToast } from '@click/ui';
import type { BuzzAudience, BuzzMediaFile, BuzzPostInput, BuzzPostKind, PartnerBuzzOverview, PartnerBuzzPost } from '@click/api';
import { apiMessage, fieldErrors } from '../../lib/format';
import { formatMoney } from '../../lib/money';
import { useSavePost, useUploadMedia } from './queries';

const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const VIDEO_TYPES = ['video/mp4', 'video/webm', 'video/quicktime'];
const RUNS = [1, 3, 7, 14, 30];

/** `datetime-local` value (local time) for a Date. */
function local(d: Date) {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

function initialRun(post?: PartnerBuzzPost) {
  if (!post?.expiresAt) return { days: 7, until: '' };
  const start = post.publishAt ? new Date(post.publishAt).getTime() : Date.now();
  const days = Math.round((new Date(post.expiresAt).getTime() - start) / 86_400_000);
  return RUNS.includes(days) ? { days, until: '' } : { days: 0, until: local(new Date(post.expiresAt)) };
}

/**
 * Create or edit a Buzz post: media, words, and the one Click action it leads to. The button can only point at the
 * partner's own live listings (the server checks again); Click reviews the post before customers see it.
 */
export function BuzzComposer({ data, post, onDone }: { data: PartnerBuzzOverview; post?: PartnerBuzzPost; onDone: () => void }) {
  const save = useSavePost();
  const upload = useUploadMedia();
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const firstListing = data.listings[0];
  const [kind, setKind] = useState<BuzzPostKind>(post?.kind ?? 'update');
  const [headline, setHeadline] = useState(post?.headline ?? '');
  const [caption, setCaption] = useState(post?.caption ?? '');
  const [media, setMedia] = useState<BuzzMediaFile[]>(post?.media ?? []);
  const [audience, setAudience] = useState<BuzzAudience>(post?.audience ?? 'public');
  const [listingKey, setListingKey] = useState(post?.targetType ? `${post.targetType}:${post.targetId}` : firstListing ? `${firstListing.type}:${firstListing.id}` : '');
  const listing = data.listings.find((l) => `${l.type}:${l.id}` === listingKey);
  const [cta, setCta] = useState(post?.cta || listing?.ctas[0] || '');
  const [productId, setProductId] = useState(post?.product?.id ?? '');
  const [offerId, setOfferId] = useState(post?.offer?.id ?? '');
  const [schedule, setSchedule] = useState(Boolean(post?.publishAt && new Date(post.publishAt) > new Date()));
  const [startAt, setStartAt] = useState(post?.publishAt ? local(new Date(post.publishAt)) : local(new Date(Date.now() + 3_600_000)));
  const [run, setRun] = useState(initialRun(post));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(0);

  const products = useMemo(() => data.products.filter((p) => p.storeId === listing?.id), [data.products, listing]);
  const offers = useMemo(() => data.offers.filter((o) => o.storeId === listing?.id), [data.offers, listing]);
  const product = products.find((p) => p.id === productId);
  const reviewed = post && !['draft', 'rejected'].includes(post.status);
  const ctaLabel = (c: string) => data.ctaLabels.find((x) => x.value === c)?.label ?? c;

  function pickListing(key: string) {
    setListingKey(key);
    const l = data.listings.find((x) => `${x.type}:${x.id}` === key);
    setCta(l?.ctas[0] ?? '');
    setProductId('');
    setOfferId('');
  }

  async function addFiles(files: FileList | null) {
    if (!files) return;
    for (const file of Array.from(files)) {
      if (media.length + uploading >= data.limits.media) { toast(`Add up to ${data.limits.media} photos or videos.`, 'error'); break; }
      const isVideo = VIDEO_TYPES.includes(file.type);
      if (!isVideo && !IMAGE_TYPES.includes(file.type)) { toast(`${file.name}: use JPG, PNG, WebP, MP4 or WebM.`, 'error'); continue; }
      if (isVideo && media.some((m) => m.kind === 'video')) { toast('Add at most one video per post.', 'error'); continue; }
      const limit = (isVideo ? data.limits.videoMb : data.limits.imageMb) * 1024 * 1024;
      if (file.size > limit) { toast(`${file.name} is too large (max ${isVideo ? data.limits.videoMb : data.limits.imageMb} MB).`, 'error'); continue; }
      setUploading((n) => n + 1);
      try {
        const m = await upload.mutateAsync(file);
        setMedia((xs) => [...xs, m]);
      } catch (err) {
        toast(apiMessage(err), 'error');
      } finally {
        setUploading((n) => n - 1);
      }
    }
    if (fileRef.current) fileRef.current.value = '';
  }

  function move(i: number, d: -1 | 1) {
    setMedia((xs) => {
      const next = [...xs];
      const [m] = next.splice(i, 1);
      if (m) next.splice(i + d, 0, m);
      return next;
    });
  }

  function body(submit: boolean): BuzzPostInput {
    const start = schedule ? new Date(startAt) : new Date();
    const end = run.days ? new Date(start.getTime() + run.days * 86_400_000) : run.until ? new Date(run.until) : null;
    return {
      kind, headline: headline.trim(), caption: caption.trim(), audience, cta: listing ? cta : '',
      targetType: listing?.type ?? '', targetId: listing?.id ?? '', productId: productId || null, offerId: offerId || null,
      publishAt: schedule ? start.toISOString() : null, expiresAt: end ? end.toISOString() : null,
      mediaIds: media.map((m) => m.id), submit,
    };
  }

  function send(submit: boolean) {
    setErrors({}); setError(null);
    save.mutate({ id: post?.id, body: body(submit) }, {
      onSuccess: (p) => { toast(p.status === 'in_review' ? 'Sent to Click for review' : 'Draft saved'); onDone(); },
      onError: (err) => { setErrors(fieldErrors(err)); setError(apiMessage(err)); },
    });
  }

  const cover = media[0];
  return (
    <form className="mod editor buzzc" noValidate onSubmit={(e) => { e.preventDefault(); send(true); }}>
      <h2 className="mod__title">{post ? 'Edit post' : 'New Buzz post'}</h2>
      {reviewed && <p className="ops__banner"><Icon name="alert" size={16} /><span>Saving changes takes this post off Buzz until Click reviews it again.</span></p>}
      <div className="buzzc__grid">
        <div className="editor">
          <fieldset className="field">
            <legend className="field__label">What’s it about?</legend>
            <div className="seg seg--wrap">
              {data.kinds.map((k) => (
                <button key={k.value} type="button" className={`seg__btn ${kind === k.value ? 'is-active' : ''}`} aria-pressed={kind === k.value}
                  onClick={() => setKind(k.value)}>{k.label}</button>
              ))}
            </div>
          </fieldset>

          <div className="field">
            <span className="field__label" id="buzz-media-l">Photos or a short video</span>
            <ul className="buzzc__media" aria-labelledby="buzz-media-l">
              {media.map((m, i) => (
                <li key={m.id} className="buzzc__thumb">
                  {m.kind === 'video' ? <video src={m.url} muted playsInline preload="metadata" /> : <img src={m.thumb || m.url} alt="" />}
                  {m.kind === 'video' && <span className="buzzc__badge"><Icon name="play" size={12} /> Video</span>}
                  <span className="buzzc__thumb-actions">
                    <button type="button" className="icon-btn icon-btn--sm" aria-label="Move earlier" disabled={i === 0} onClick={() => move(i, -1)}><Icon name="back" size={14} /></button>
                    <button type="button" className="icon-btn icon-btn--sm" aria-label="Move later" disabled={i === media.length - 1} onClick={() => move(i, 1)}><Icon name="right" size={14} /></button>
                    <button type="button" className="icon-btn icon-btn--sm" aria-label="Remove" onClick={() => setMedia((xs) => xs.filter((x) => x.id !== m.id))}><Icon name="close" size={14} /></button>
                  </span>
                </li>
              ))}
              {Array.from({ length: uploading }, (_, i) => <li key={`u${i}`} className="buzzc__thumb buzzc__thumb--loading" aria-label="Uploading" />)}
              {media.length + uploading < data.limits.media && (
                <li>
                  <label className="buzzc__add">
                    <Icon name="camera" size={22} /><span>Add</span>
                    <input ref={fileRef} type="file" className="visually-hidden" multiple accept={[...IMAGE_TYPES, ...VIDEO_TYPES].join(',')}
                      onChange={(e) => void addFiles(e.target.files)} />
                  </label>
                </li>
              )}
            </ul>
            <span className="small muted">JPG, PNG or WebP up to {data.limits.imageMb} MB (Click optimises them); one MP4/WebM video up to {data.limits.videoMb} MB. The first one is the cover.</span>
            {errors.mediaIds && <span className="field__error">{errors.mediaIds}</span>}
          </div>

          <label className="field">
            <span className="field__label">Headline</span>
            <input className="field__input" maxLength={80} value={headline} placeholder="e.g. New Special Chicken Biryani — ₹199 today" onChange={(e) => setHeadline(e.target.value)} />
            {errors.headline && <span className="field__error">{errors.headline}</span>}
          </label>
          <label className="field">
            <span className="field__label">Caption <span className="muted">({600 - caption.length} left)</span></span>
            <textarea className="field__input" rows={3} maxLength={600} value={caption} onChange={(e) => setCaption(e.target.value)}
              placeholder="Say what’s new. Keep prices and claims accurate: Click checks them." />
            {errors.caption && <span className="field__error">{errors.caption}</span>}
          </label>

          <fieldset className="field">
            <legend className="field__label">Button</legend>
            {data.listings.length > 1 && (
              <select className="field__input" aria-label="Where the button goes" value={listingKey} onChange={(e) => pickListing(e.target.value)}>
                {data.listings.map((l) => <option key={`${l.type}:${l.id}`} value={`${l.type}:${l.id}`}>{l.title}</option>)}
              </select>
            )}
            {audience === 'partners' && <label className="check"><input type="checkbox" checked={!!listingKey} onChange={(e) => pickListing(e.target.checked && firstListing ? `${firstListing.type}:${firstListing.id}` : '')} /> Add a button</label>}
            {listing && (
              <div className="seg seg--wrap">
                {listing.ctas.map((c) => (
                  <button key={c} type="button" className={`seg__btn ${cta === c ? 'is-active' : ''}`} aria-pressed={cta === c} onClick={() => setCta(c)}>{ctaLabel(c)}</button>
                ))}
              </div>
            )}
            {listing && <span className="small muted">Opens {listing.title} in the Click app. Customers order and pay through Click.</span>}
            {(errors.targetType || errors.cta) && <span className="field__error">{errors.targetType || errors.cta}</span>}
          </fieldset>

          {(products.length > 0 || offers.length > 0) && (
            <div className="editor__grid">
              {products.length > 0 && (
                <label className="field">
                  <span className="field__label">Feature an item (optional)</span>
                  <select className="field__input" value={productId} onChange={(e) => setProductId(e.target.value)}>
                    <option value="">None</option>
                    {products.map((p) => <option key={p.id} value={p.id}>{p.name} · {formatMoney(p.price)}{p.available ? '' : ' · unavailable now'}</option>)}
                  </select>
                  {product && !product.available && <span className="small tone-danger">Customers will see it as unavailable until you switch it back on in your menu.</span>}
                  {errors.productId && <span className="field__error">{errors.productId}</span>}
                </label>
              )}
              {offers.length > 0 && (
                <label className="field">
                  <span className="field__label">Attach an offer{kind === 'offer' ? '' : ' (optional)'}</span>
                  <select className="field__input" value={offerId} onChange={(e) => setOfferId(e.target.value)}>
                    <option value="">None</option>
                    {offers.map((o) => <option key={o.id} value={o.id}>{o.title}</option>)}
                  </select>
                  {errors.offerId && <span className="field__error">{errors.offerId}</span>}
                </label>
              )}
            </div>
          )}
          {offers.length === 0 && (errors.offerId || kind === 'offer') && (
            <p className="field__error">{errors.offerId || 'An offer post needs one of your live offers. Create the offer first; Click approves it.'}</p>
          )}

          <fieldset className="field">
            <legend className="field__label">Who sees it</legend>
            <div className="seg">
              <button type="button" className={`seg__btn ${audience === 'public' ? 'is-active' : ''}`} aria-pressed={audience === 'public'} onClick={() => { setAudience('public'); if (!listing && firstListing) pickListing(`${firstListing.type}:${firstListing.id}`); }}>Customers and partners</button>
              <button type="button" className={`seg__btn ${audience === 'partners' ? 'is-active' : ''}`} aria-pressed={audience === 'partners'} onClick={() => setAudience('partners')}>Partners only</button>
            </div>
          </fieldset>

          <div className="editor__grid">
            <fieldset className="field">
              <legend className="field__label">Starts</legend>
              <div className="seg">
                <button type="button" className={`seg__btn ${!schedule ? 'is-active' : ''}`} aria-pressed={!schedule} onClick={() => setSchedule(false)}>When approved</button>
                <button type="button" className={`seg__btn ${schedule ? 'is-active' : ''}`} aria-pressed={schedule} onClick={() => setSchedule(true)}>Schedule</button>
              </div>
              {schedule && <input className="field__input" type="datetime-local" aria-label="Start date and time" value={startAt} min={local(new Date())} onChange={(e) => setStartAt(e.target.value)} />}
              {errors.publishAt && <span className="field__error">{errors.publishAt}</span>}
            </fieldset>
            <fieldset className="field">
              <legend className="field__label">Runs for</legend>
              <div className="seg seg--wrap">
                {RUNS.map((d) => (
                  <button key={d} type="button" className={`seg__btn ${run.days === d ? 'is-active' : ''}`} aria-pressed={run.days === d} onClick={() => setRun({ days: d, until: '' })}>
                    {d === 1 ? '1 day' : `${d} days`}</button>
                ))}
                <button type="button" className={`seg__btn ${run.days === 0 ? 'is-active' : ''}`} aria-pressed={run.days === 0}
                  onClick={() => setRun({ days: 0, until: run.until || local(new Date(Date.now() + 10 * 86_400_000)) })}>Until…</button>
              </div>
              {run.days === 0 && <input className="field__input" type="datetime-local" aria-label="End date and time" value={run.until} onChange={(e) => setRun({ days: 0, until: e.target.value })} />}
              {errors.expiresAt && <span className="field__error">{errors.expiresAt}</span>}
            </fieldset>
          </div>
        </div>

        <aside className="buzzc__preview" aria-label="Preview">
          <span className="small muted">Preview on Click. Buzz</span>
          <div className="bpv">
            {cover?.kind === 'video' ? <video className="bpv__media" src={cover.url} muted playsInline preload="metadata" />
              : cover ? <img className="bpv__media" src={cover.url} alt="" /> : <span className="bpv__media bpv__media--art" aria-hidden="true"><Icon name="sparkle" size={48} /></span>}
            <span className="bpv__shade" aria-hidden="true" />
            <span className="bpv__tag">{data.kinds.find((k) => k.value === kind)?.label}</span>
            <div className="bpv__body">
              <span className="bpv__handle">@{listing?.handle ?? 'you'}</span>
              <strong>{headline || 'Your headline'}</strong>
              {caption && <span className="bpv__caption">{caption}</span>}
              {product && <span className="bpv__item">{product.name} · {formatMoney(product.price)}{product.available ? '' : ' · Unavailable'}</span>}
              {listing && cta && <span className="bpv__cta">{ctaLabel(cta)} <Icon name="right" size={14} /></span>}
            </div>
          </div>
        </aside>
      </div>

      {!data.canPublish && <p className="small muted">You can save drafts now. Click needs to verify your account before posts can be submitted.</p>}
      {error && <p className="field__error" role="alert">{error}</p>}
      <div className="dialog__actions">
        <button type="button" className="btn btn--ghost" onClick={onDone}>Cancel</button>
        {!reviewed && <Button type="button" variant="outline" loading={save.isPending && !save.variables?.body.submit} disabled={uploading > 0} onClick={() => send(false)}>Save draft</Button>}
        <Button type="submit" loading={save.isPending && !!save.variables?.body.submit} disabled={uploading > 0 || !data.canPublish}>
          {reviewed ? 'Save and send for review' : 'Send for review'}</Button>
      </div>
    </form>
  );
}
