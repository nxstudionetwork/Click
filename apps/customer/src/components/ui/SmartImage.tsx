import { useState } from 'react';

/** Image with a deterministic branded fallback when the URL is empty or fails. */
function hue(seed: string) {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) % 360;
  return h;
}

function initials(name: string) {
  return name.split(/\s+/).filter((w) => /[a-z]/i.test(w)).slice(0, 2).map((w) => w[0]!.toUpperCase()).join('');
}

export function SmartImage({ src, alt, className = '', children }: { src?: string; alt: string; className?: string; children?: React.ReactNode }) {
  const [failed, setFailed] = useState(false);
  const h = hue(alt);
  return (
    <div className={`img ${className}`}>
      {src && !failed ? (
        <img src={src} alt={alt} loading="lazy" decoding="async" onError={() => setFailed(true)} />
      ) : (
        <div
          className="img__fallback"
          role="img"
          aria-label={alt}
          style={{ background: `linear-gradient(135deg, hsl(${h} 70% 62%), hsl(${(h + 40) % 360} 65% 45%))` }}
        >
          {initials(alt)}
        </div>
      )}
      {children}
    </div>
  );
}
