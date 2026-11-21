import { NavLink, Outlet } from 'react-router-dom';
import { Icon, type IconName } from '@click/ui';
import { useAccess } from '../../session/access';
import { PageHeader } from '../../components/ui';

const SECTIONS: { label: string; items: { to: string; label: string; icon: IconName; perm?: string }[] }[] = [
  { label: 'Personal', items: [
    { to: 'preferences', label: 'Profile & preferences', icon: 'user' },
    { to: 'security', label: 'Security & sessions', icon: 'shield' },
  ] },
  { label: 'Organization', items: [
    { to: 'organization', label: 'Structure', icon: 'building', perm: 'organization.unit.view' },
  ] },
  { label: 'Administration', items: [
    { to: 'users', label: 'Users', icon: 'team', perm: 'identity.user.view' },
    { to: 'roles', label: 'Roles & permissions', icon: 'key', perm: 'access.role.view' },
    { to: 'workflows', label: 'Workflows & approvals', icon: 'flow', perm: 'workflows.policy.view' },
    { to: 'integrations', label: 'Integrations', icon: 'plug', perm: 'integrations.integration.view' },
    { to: 'audit', label: 'Audit trail', icon: 'history', perm: 'audit.event.view' },
    { to: 'system', label: 'System', icon: 'settings', perm: 'system.health.view' },
  ] },
];

/** Settings shows only what the person can manage; each page and the API re-check on their own. */
export function SettingsLayout() {
  const access = useAccess();
  const sections = SECTIONS.map((s) => ({ ...s, items: s.items.filter((i) => !i.perm || access.can(i.perm) || access.mfaBlocked(i.perm)) }))
    .filter((s) => s.items.length);
  return (
    <>
      <PageHeader title="Settings" />
      <div className="split">
        <nav className="sidenav" aria-label="Settings">
          {sections.map((s) => (
            <div key={s.label} style={{ display: 'contents' }}>
              <div className="sidenav__label">{s.label}</div>
              {s.items.map((i) => <NavLink key={i.to} to={i.to}><Icon name={i.icon} size={16} />{i.label}</NavLink>)}
            </div>
          ))}
        </nav>
        <div style={{ minWidth: 0 }}><Outlet /></div>
      </div>
    </>
  );
}
