import { useId } from 'react';

/**
 * Buddy's mark: a Click.-gradient orb with a calm face. Eyes blink now and then, the glow breathes, and while Buddy
 * listens or thinks (`state`) the face responds. Pure SVG + CSS, so it is crisp at any size and follows White/Dark
 * through the ring colour. Motion stops for people who ask for reduced motion.
 */
export function BuddyMark({ size = 28, state = 'idle', className = '' }: { size?: number; state?: 'idle' | 'listening' | 'thinking'; className?: string }) {
  const id = useId().replace(/:/g, '');
  return (
    <svg className={`buddy-mark buddy-mark--${state} ${className}`} width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
      <defs>
        <linearGradient id={`bm-g-${id}`} x1="6" y1="4" x2="42" y2="44" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#22d3ee" />
          <stop offset=".45" stopColor="#4f5bff" />
          <stop offset="1" stopColor="#a855f7" />
        </linearGradient>
        <radialGradient id={`bm-h-${id}`} cx=".32" cy=".26" r=".6">
          <stop offset="0" stopColor="#fff" stopOpacity=".55" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle className="buddy-mark__glow" cx="24" cy="24" r="22" fill={`url(#bm-g-${id})`} opacity=".28" />
      <circle cx="24" cy="24" r="18.5" fill={`url(#bm-g-${id})`} />
      <circle cx="24" cy="24" r="18.5" fill={`url(#bm-h-${id})`} />
      <circle className="buddy-mark__ring" cx="24" cy="24" r="18.5" fill="none" strokeWidth="1.5" />
      <g className="buddy-mark__eyes" fill="#fff">
        <rect x="16.2" y="19" width="4.2" height="7.4" rx="2.1" />
        <rect x="27.6" y="19" width="4.2" height="7.4" rx="2.1" />
      </g>
      <path className="buddy-mark__smile" d="M19 30.2c2.9 2.6 7.1 2.6 10 0" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
      <path className="buddy-mark__spark" d="M38.5 7.5l1.1 2.6 2.6 1.1-2.6 1.1-1.1 2.6-1.1-2.6-2.6-1.1 2.6-1.1z" fill="#fbbf24" />
    </svg>
  );
}
