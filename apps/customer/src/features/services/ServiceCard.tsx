import { Link } from 'react-router-dom';
import type { ClickService } from '../../config/services';
import { Icon } from '../../components/ui';

export function ServiceCard({ service, detailed = false }: { service: ClickService; detailed?: boolean }) {
  const live = service.status === 'live';
  return (
    <Link to={service.path} className={`service ${live ? 'service--live' : 'service--soon'}`}>
      {!live && <span className="badge">Soon</span>}
      <span className="service__icon"><Icon name={service.icon} /></span>
      <span className="service__name">{service.name}</span>
      {detailed && <span className="small muted">{service.tagline}</span>}
    </Link>
  );
}
