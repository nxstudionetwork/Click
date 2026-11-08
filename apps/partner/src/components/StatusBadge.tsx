import { Icon, type IconName } from '@click/ui';
import type { PartnerStatus } from '@click/api';

/** Status is always shown with text and an icon, never colour alone. Only server state is displayed. */
const STYLE: Record<PartnerStatus, { tone: string; icon: IconName }> = {
  draft: { tone: 'neutral', icon: 'edit' },
  profile_completed: { tone: 'info', icon: 'check' },
  verification_pending: { tone: 'pending', icon: 'clock' },
  verified: { tone: 'success', icon: 'shield' },
  active: { tone: 'success', icon: 'check' },
  rejected: { tone: 'danger', icon: 'alert' },
  suspended: { tone: 'danger', icon: 'alert' },
  inactive: { tone: 'neutral', icon: 'clock' },
};

export function StatusBadge({ status, label, onDark = false }: { status: PartnerStatus; label: string; onDark?: boolean }) {
  const s = STYLE[status] ?? STYLE.draft;
  return (
    <span className={`status status--${s.tone} ${onDark ? 'status--on-dark' : ''}`}>
      <Icon name={s.icon} size={14} />
      <span>{label}</span>
    </span>
  );
}
