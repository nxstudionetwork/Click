import { useState } from 'react';
import type { ShopImage as Img } from '@click/api';
import { Icon, type IconName } from '../../components/ui';

const ICONS = new Set<string>(['device', 'phone', 'shirt', 'shoe', 'home', 'beauty', 'appliance', 'book', 'dumbbell', 'toy', 'baby', 'briefcase', 'gem', 'paw', 'edit', 'sofa', 'headphones', 'bag']);

/**
 * A product photo (responsive srcset, lazy, never stretched) or, when the seller hasn't uploaded one, an honest
 * branded placeholder with the category icon. Click. never borrows stock photos for specific products.
 */
export function ShopImage({ image, alt, icon, brand, sizes = '(min-width: 1024px) 22vw, 46vw', eager = false }: {
  image: Img | null; alt: string; icon?: string; brand?: string; sizes?: string; eager?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const iconName = (icon && ICONS.has(icon) ? icon : 'bag') as IconName;
  return (
    <div className="pimg">
      {image?.src && !failed ? (
        <img src={image.src} srcSet={image.srcSet || undefined} sizes={image.srcSet ? sizes : undefined} alt={image.alt || alt}
          loading={eager ? 'eager' : 'lazy'} decoding="async" width={image.width ?? undefined} height={image.height ?? undefined} onError={() => setFailed(true)} />
      ) : (
        <div className="pimg__ph" role="img" aria-label={`${alt} (no photo yet)`}>
          <Icon name={iconName} size={40} />
          {brand && <span className="pimg__brand">{brand}</span>}
        </div>
      )}
    </div>
  );
}
