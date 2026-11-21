import { Link } from 'react-router-dom';
import { Icon } from '../../components/ui';
import { SERVICES } from '../../config/services';

/** Horizontal service row. Every tile has a real route; services not launched yet are marked "Soon". */
export function QuickServices() {
  return (
    <nav className="qs" aria-label="Click. services">
      <ul className="qs__list">
        {SERVICES.map((s) => (
          <li key={s.id}>
            <Link to={s.path} className={`qs__item ${s.status === 'soon' ? 'qs__item--soon' : ''}`} data-theme={s.theme}
              aria-label={`${s.name}${s.status === 'soon' ? ', launching soon' : ''}`}>
              <span className="qs__icon"><Icon name={s.icon} size={24} /></span>
              <span className="qs__name">{s.short ?? s.name}</span>
              {s.status === 'soon' && <span className="qs__soon">Soon</span>}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
