import { Link } from 'react-router-dom';
import { Icon } from '../../components/ui';
import { BuzzPreviewCard } from '../buzz/BuzzCard';
import { useBuzz } from '../buzz/useBuzz';
import { RailSkeleton, SectionEmpty, SectionError } from './HomeSection';

/** Click. Buzz on Home: its own energetic band, not just another card row. */
export function BuzzPreview() {
  const buzz = useBuzz(8);
  return (
    <section className="buzz-band" data-theme="buzz" aria-labelledby="buzz-h">
      <div className="buzz-band__head">
        <div>
          <h2 id="buzz-h"><span className="buzz-band__logo">Click.</span> BUZZ</h2>
          <p>Instants from places and shows you can act on</p>
        </div>
        <Link to="/buzz" className="btn btn--sm btn--buzz">View Buzz <Icon name="right" size={14} /></Link>
      </div>
      {buzz.isPending ? <RailSkeleton variant="tall" count={5} /> : buzz.isError ? <SectionError onRetry={() => buzz.refetch()} /> :
        buzz.data.results.length === 0 ? <SectionEmpty icon="play" title="Nothing buzzing yet" text="Offers, shows and new places will appear here." /> : (
          <div className="rail rail--story" role="list" aria-label="Buzz instants">
            {buzz.data.results.map((i) => <div key={i.id} className="rail__item" role="listitem"><BuzzPreviewCard item={i} /></div>)}
          </div>
        )}
    </section>
  );
}
