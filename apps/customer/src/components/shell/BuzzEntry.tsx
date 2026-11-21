import { Link, useLocation } from 'react-router-dom';
import { Icon } from '../ui';

/** Persistent Click. Buzz handle attached to the right edge, above the bottom navigation on phones. */
export function BuzzEntry() {
  const { pathname } = useLocation();
  if (/^\/(checkout|cart|shows\/)/.test(pathname)) return null;
  return (
    <Link to="/buzz" className="buzz-entry" data-theme="buzz" aria-label="Open Click. Buzz">
      <span className="buzz-entry__pulse" aria-hidden="true" />
      <Icon name="play" size={18} />
      <span className="buzz-entry__label">Buzz</span>
    </Link>
  );
}
