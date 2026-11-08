import { ClickMark, Icon } from '@click/ui';
import type { Partner } from '@click/api';
import { iconFor, visualFor } from '../config/visuals';
import { StatusBadge } from './StatusBadge';

/** Only public-safe fields: name, Partner ID, category, status. No phone, address, email or internal IDs. */
export interface CardData {
  businessName: string;
  partnerCode: string;
  categoryName: string;
  typeName: string;
  typeSlug: string;
  categoryIcon: string;
  status: Partner['status'];
  statusLabel: string;
}

export function cardData(partner: Partner): CardData | null {
  if (!partner.partnerCode) return null;
  return {
    businessName: partner.businessName,
    partnerCode: partner.partnerCode,
    categoryName: partner.category.name,
    typeName: partner.partnerType.name,
    typeSlug: partner.partnerType.slug,
    categoryIcon: partner.category.icon,
    status: partner.status,
    statusLabel: partner.statusLabel,
  };
}

export function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join('') || 'CP';
}

export function PartnerCard({ data, compact = false }: { data: CardData; compact?: boolean }) {
  const accent = visualFor(data.typeSlug).accent;
  return (
    <article className={`pcard ${compact ? 'pcard--compact' : ''}`} style={{ ['--pcard-accent' as string]: accent }}
      aria-label={`Click Partner card for ${data.businessName}, Partner ID ${data.partnerCode}`}>
      <div className="pcard__glow" aria-hidden="true" />
      <div className="pcard__top">
        <span className="pcard__brand"><ClickMark size={30} /><span>CLICK PARTNER</span></span>
        <span className="pcard__chip" aria-hidden="true"><Icon name={iconFor(data.categoryIcon)} size={20} /></span>
      </div>
      <div className="pcard__identity">
        <span className="pcard__avatar" aria-hidden="true">{initials(data.businessName)}</span>
        <div className="pcard__name-wrap">
          <h2 className="pcard__name">{data.businessName}</h2>
          <p className="pcard__type">{data.typeName}</p>
        </div>
      </div>
      <div className="pcard__code">
        <span className="pcard__label">Partner ID</span>
        <span className="pcard__code-value">{data.partnerCode}</span>
      </div>
      <dl className="pcard__meta">
        <div><dt>Partner category</dt><dd>{data.categoryName}</dd></div>
        <div><dt>Status</dt><dd><StatusBadge status={data.status} label={data.statusLabel} onDark /></dd></div>
      </dl>
    </article>
  );
}
