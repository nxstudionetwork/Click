import { Link } from 'react-router-dom';
import { useAuth } from '../../auth/AuthProvider';

/** Header profile entry: always goes to the customer's Profile page (no popup). */
export function ProfileButton() {
  const { user, status } = useAuth();
  if (status === 'loading') return <span className="avatar avatar--ghost" aria-hidden="true" />;
  if (status !== 'authenticated') return <Link to="/login" className="btn btn--primary btn--sm header__signin">Sign in</Link>;
  const initial = (user?.fullName || user?.email || '?').trim()[0]!.toUpperCase();
  return (
    <Link to="/account" className="avatar" aria-label="Your profile">
      {user?.avatarUrl ? <img src={user.avatarUrl} alt="" /> : initial}
    </Link>
  );
}
