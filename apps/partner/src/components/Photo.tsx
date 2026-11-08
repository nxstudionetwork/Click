import { useState } from 'react';
import { photoSet } from '../config/visuals';

/** Responsive real photograph with a branded gradient fallback if it fails to load. */
export function Photo({ photo, alt, sizes = '100vw', eager = false, className = '' }: {
  photo: string; alt: string; sizes?: string; eager?: boolean; className?: string;
}) {
  const [failed, setFailed] = useState(false);
  if (failed) return <div className={`photo photo--fallback ${className}`} role="img" aria-label={alt} />;
  const { src, srcSet } = photoSet(photo);
  return (
    <img
      className={`photo ${className}`} src={src} srcSet={srcSet} sizes={sizes} alt={alt}
      loading={eager ? 'eager' : 'lazy'} decoding="async" fetchPriority={eager ? 'high' : 'auto'}
      onError={() => setFailed(true)}
    />
  );
}
