import { Logo } from '@click/ui';
import { StoryReel } from '../components/StoryReel';
import { ECOSYSTEM_STORY } from '../config/visuals';

const VERBS = ['Operate', 'Receive', 'Serve', 'Deliver', 'Earn', 'Grow'];

/** Shown while the session is restored. Purely presentational; it never claims a state that isn't real. */
export function Splash({ leaving }: { leaving: boolean }) {
  return (
    <div className={`splash ${leaving ? 'is-leaving' : ''}`} role="status" aria-live="polite" aria-label="Opening Click Partner">
      <div className="splash__bg" aria-hidden="true" />
      <div className="splash__inner">
        <div className="splash__brand">
          <Logo tone="dark" product="Partner" size={40} />
          <p className="splash__tagline">Your business. Your services. Your Click.</p>
        </div>
        <StoryReel scenes={ECOSYSTEM_STORY} interval={1400} label="Click Partner ecosystem" sizes="(min-width: 720px) 420px, 80vw" eagerFirst className="reel--splash" />
        <ul className="splash__verbs" aria-hidden="true">
          {VERBS.map((v, i) => <li key={v} style={{ animationDelay: `${i * 140}ms` }}>{v}</li>)}
        </ul>
        <div className="splash__progress" aria-hidden="true"><span /></div>
      </div>
    </div>
  );
}
