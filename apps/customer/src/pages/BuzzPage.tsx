import { useEffect, useRef } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Icon } from '../components/ui';
import { BuzzMedia, KIND_ICON } from '../features/buzz/BuzzCard';
import { useBuzz } from '../features/buzz/useBuzz';

/**
 * Click. Buzz: vertical instants. Each one is a real Click. record with exactly one action into the matching flow
 * (order, shop, book). Own full-screen layout, outside the normal header and bottom navigation.
 */
export function BuzzPage() {
  const buzz = useBuzz(30);
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const feed = useRef<HTMLDivElement>(null);
  const start = params.get('item');

  useEffect(() => {
    if (!start || !buzz.data) return;
    const el = feed.current?.querySelector<HTMLElement>(`[data-id="${CSS.escape(start)}"]`);
    el?.scrollIntoView({ block: 'start' });
  }, [start, buzz.data]);

  return (
    <div className="buzz-page" data-theme="buzz">
      <header className="buzz-page__head">
        <button className="icon-btn icon-btn--glass" aria-label="Back" onClick={() => (window.history.length > 1 ? navigate(-1) : navigate('/'))}><Icon name="back" /></button>
        <h1><span>Click.</span> BUZZ</h1>
        <Link to="/" className="icon-btn icon-btn--glass" aria-label="Click. home"><Icon name="home" /></Link>
      </header>

      {buzz.isPending ? (
        <div className="buzz-feed"><div className="buzz-slide"><div className="skeleton buzz-slide__card" /></div></div>
      ) : buzz.isError ? (
        <div className="buzz-page__state" role="alert">
          <h2>Something went wrong.</h2><p>We couldn’t load Buzz right now.</p>
          <button className="btn btn--buzz" onClick={() => buzz.refetch()}>Try again</button>
        </div>
      ) : buzz.data.results.length === 0 ? (
        <div className="buzz-page__state">
          <h2>Nothing buzzing yet</h2><p>Offers, shows and new places will appear here.</p>
          <Link to="/explore" className="btn btn--buzz">Explore Click.</Link>
        </div>
      ) : (
        <div className="buzz-feed" ref={feed} aria-label="Buzz instants">
          {buzz.data.results.map((item, i) => (
            <article key={item.id} className="buzz-slide" data-id={item.id} aria-label={`${item.title}, ${i + 1} of ${buzz.data.results.length}`}>
              <div className="buzz-slide__card" data-theme={item.theme}>
                <BuzzMedia item={item} eager={i < 2} />
                <span className="buzz-slide__shade" aria-hidden="true" />
                <span className="buzz-card__tag"><Icon name={KIND_ICON[item.kind]} size={12} />{item.tag}</span>
                <div className="buzz-slide__body">
                  <span className="buzz-card__handle">@{item.source.handle}</span>
                  <h2>{item.title}</h2>
                  {item.body && <p>{item.body}</p>}
                  <Link to={item.action.path} className="btn btn--light buzz-slide__cta">{item.action.label} <Icon name="right" size={16} /></Link>
                </div>
              </div>
            </article>
          ))}
          <div className="buzz-slide buzz-slide--end">
            <p>You’re all caught up.</p>
            <Link to="/" className="btn btn--buzz">Back to Home</Link>
          </div>
        </div>
      )}
    </div>
  );
}
