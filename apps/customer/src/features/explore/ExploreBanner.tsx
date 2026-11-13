import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Icon } from '../../components/ui';
import { advanceBanner, currentBannerIndex, EXPLORE_BANNERS, type ExploreBanner as Banner } from '../../config/explore';

/** The Explore banner: shows the next banner in the rotation each time Explore opens (only its image loads). */
export function ExploreBanner({ banners = EXPLORE_BANNERS }: { banners?: Banner[] }) {
  const [index] = useState(() => currentBannerIndex(banners.length));
  // Idempotent (writes index + 1), so React's development double-mount doesn't skip a banner.
  useEffect(() => { advanceBanner(index, banners.length); }, [index, banners.length]);
  const b = banners[index]!;
  const photo = b.visual === 'brand' ? null : `/media/onboarding/${b.visual}`;

  return (
    <section className="xbanner" data-theme={b.theme} aria-roledescription="banner" aria-label={`${b.title} ${b.titleAccent ?? ''}`.trim()}>
      {photo && (
        <img className="xbanner__photo" src={`${photo}-640.webp`} srcSet={`${photo}-640.webp 640w, ${photo}-1280.webp 1280w`}
          sizes="(min-width: 1024px) 960px, 100vw" alt="" decoding="async" fetchPriority="high" />
      )}
      <span className="xbanner__shade" aria-hidden="true" />
      <div className="xbanner__copy">
        <span className="xbanner__eyebrow">{b.eyebrow}</span>
        <h2 className="xbanner__title">{b.title}{b.titleAccent && <><br /><span>{b.titleAccent}</span></>}</h2>
        <p className="xbanner__sub">{b.subtitle}</p>
        {b.action && <Link to={b.action.to} className="btn btn--light xbanner__cta">{b.action.label} <Icon name="right" size={16} /></Link>}
      </div>
      {b.visual === 'brand' && (
        <div className="xbanner__brand" aria-hidden="true">
          <img src="/brand/click-icon-192.png" srcSet="/brand/click-icon-192.png 1x, /brand/click-icon-512.png 2x" width={104} height={104} alt="" />
          {b.icons?.map((name, i) => <span key={name} className={`xbanner__chip xbanner__chip--${i}`}><Icon name={name} size={16} /></span>)}
        </div>
      )}
      <span className="xbanner__dots" aria-hidden="true">
        {banners.map((x, i) => <span key={x.id} className={i === index ? 'on' : ''} />)}
      </span>
    </section>
  );
}
