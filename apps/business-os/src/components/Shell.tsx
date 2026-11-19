import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Icon, type IconName } from '@click/ui';
import { api } from '../lib/api';
import { relative } from '../lib/format';
import { useOS, useOSSession } from '../session/OSSession';
import { AIPanel } from './AIPanel';
import { CommandPalette } from './CommandPalette';
import { Avatar } from './ui';

const COLLAPSE_KEY = 'click-os:sidebar-collapsed';

function readCollapsed(): boolean {
  try { return localStorage.getItem(COLLAPSE_KEY) === '1'; } catch { return false; }
}

export function Shell({ children }: { children: ReactNode }) {
  const ctx = useOS();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [navOpen, setNavOpen] = useState(false);
  const [palette, setPalette] = useState(false);
  const [ai, setAi] = useState(false);

  useEffect(() => { setNavOpen(false); }, [location.pathname]);
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette(true); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);

  const toggleCollapsed = () => setCollapsed((c) => {
    try { localStorage.setItem(COLLAPSE_KEY, c ? '0' : '1'); } catch { /* storage unavailable */ }
    return !c;
  });

  const summary = useQuery({ queryKey: ['os', 'notifications', 'summary'], queryFn: api.notifications.summary, refetchInterval: 60_000 });
  const inbox = useQuery({ queryKey: ['os', 'approvals', 'count'], queryFn: () => api.approvals.list('inbox'), refetchInterval: 120_000 });
  const badges: Record<string, number> = { approvals: inbox.data?.results.length ?? 0, notifications: summary.data?.unread ?? 0 };

  return (
    <div className={`shell ${collapsed ? 'shell--collapsed' : ''} ${navOpen ? 'shell--nav-open' : ''}`}>
      <a href="#main" className="skip-link">Skip to content</a>
      <aside className="sidebar" aria-label="Main navigation">
        <div className="sidebar__top">
          <Link to="/home" className="sidebar__brand" style={{ textDecoration: 'none' }} aria-label="Click Business OS home">
            <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9" fill="#5B3DF5" /><circle cx="16" cy="16" r="7.5" fill="none" stroke="#fff" strokeWidth="3" /><circle cx="16" cy="16" r="2.6" fill="#14C8A0" /></svg>
            <span className="sidebar__brand-text">CLICK<small>BUSINESS OS</small></span>
          </Link>
        </div>
        <nav className="sidebar__nav">
          {ctx.navigation.map((g) => (
            <div className="nav-group" key={g.key}>
              <div className="nav-group__label">{g.label}</div>
              {g.items.map((it) => (
                <NavLink key={it.key} to={it.path} className="nav-item" title={collapsed ? it.label : undefined}>
                  <Icon name={it.icon as IconName} size={18} />
                  <span className="nav-item__label">{it.label}</span>
                  {badges[it.key] ? <span className="nav-item__badge">{badges[it.key]! > 99 ? '99+' : badges[it.key]}</span> : null}
                  {it.status === 'foundation' && !badges[it.key] && <span className="nav-item__soon">SOON</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar__foot">
          <button className="sidebar__collapse" onClick={toggleCollapsed} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
            <Icon name="sidebar" size={18} /><span>Collapse</span>
          </button>
        </div>
      </aside>
      <div className="scrim" onClick={() => setNavOpen(false)} aria-hidden="true" />
      <div className="main">
        <Header unread={summary.data?.unread ?? 0} critical={summary.data?.critical ?? 0} onMenu={() => setNavOpen(true)}
                onSearch={() => setPalette(true)} onAI={() => setAi(true)} />
        <main id="main" className="content" tabIndex={-1}>{children}</main>
      </div>
      {palette && <CommandPalette onClose={() => setPalette(false)} />}
      {ai && <AIPanel onClose={() => setAi(false)} />}
    </div>
  );
}

function useOutside(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) close(); };
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
    document.addEventListener('mousedown', h);
    document.addEventListener('keydown', k);
    return () => { document.removeEventListener('mousedown', h); document.removeEventListener('keydown', k); };
  }, [open, close]);
  return ref;
}

function Header({ unread, critical, onMenu, onSearch, onAI }: { unread: number; critical: number; onMenu: () => void; onSearch: () => void; onAI: () => void }) {
  const ctx = useOS();
  const { logout } = useOSSession();
  const navigate = useNavigate();
  const [menu, setMenu] = useState<'none' | 'user' | 'notif'>('none');
  const close = useCallback(() => setMenu('none'), []);
  const userRef = useOutside(menu === 'user', close);
  const notifRef = useOutside(menu === 'notif', close);
  const mfa = ctx.account.mfaEnabled;

  return (
    <header className="header">
      <button className="icon-btn header__menu" onClick={onMenu} aria-label="Open navigation"><Icon name="menu" size={20} /></button>
      <span className="header__org" title="Organization">
        <Icon name="building" size={16} />{ctx.organization.name}
        {ctx.orgContext.location && <span className="muted">· {ctx.orgContext.location.name}</span>}
      </span>
      <button className="header__search" onClick={onSearch} aria-label="Search Business OS">
        <Icon name="search" size={16} /><span>Search people, approvals, tasks…</span><kbd>Ctrl K</kbd>
      </button>
      <div className="header__actions">
        <span className={`session-pill ${mfa ? '' : 'session-pill--warn'}`} title={mfa ? 'Two-step verification is on' : 'Two-step verification is off'}>
          <Icon name={mfa ? 'shield' : 'alert'} size={13} />{mfa ? 'Secured' : 'Add 2-step'}
        </span>
        <button className="icon-btn" onClick={onAI} aria-label="Click Business AI" title="Click Business AI"><Icon name="sparkle" size={19} /></button>
        <div style={{ position: 'relative' }} ref={notifRef}>
          <button className="icon-btn" onClick={() => setMenu(menu === 'notif' ? 'none' : 'notif')} aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`} aria-expanded={menu === 'notif'}>
            <Icon name="bell" size={19} />
            {unread > 0 && <span className="icon-btn__dot" style={critical ? undefined : { background: 'var(--c-brand)' }}>{unread > 9 ? '9+' : unread}</span>}
          </button>
          {menu === 'notif' && <NotificationsPopover onClose={close} />}
        </div>
        <Link to="/help" className="icon-btn" aria-label="Help" title="Help"><Icon name="help" size={19} /></Link>
        <div style={{ position: 'relative' }} ref={userRef}>
          <button className="user-btn" onClick={() => setMenu(menu === 'user' ? 'none' : 'user')} aria-haspopup="menu" aria-expanded={menu === 'user'}>
            <Avatar name={ctx.user.fullName} src={ctx.user.avatarUrl} />
            <span className="user-btn__name ellipsis">{ctx.user.fullName}</span>
          </button>
          {menu === 'user' && (
            <div className="popover" role="menu">
              <div style={{ padding: '8px 10px 10px' }}>
                <strong className="ellipsis" style={{ display: 'block' }}>{ctx.user.fullName}</strong>
                <span className="xs muted">{ctx.employee?.designation ?? ctx.account.kind} · {ctx.roles.map((r) => r.name).join(', ') || 'No roles'}</span>
              </div>
              <div className="menu-sep" />
              <Link className="menu-item" to="/profile" onClick={close} role="menuitem"><Icon name="user" size={16} />Profile</Link>
              <Link className="menu-item" to="/settings/preferences" onClick={close} role="menuitem"><Icon name="settings" size={16} />Settings</Link>
              <Link className="menu-item" to="/settings/security" onClick={close} role="menuitem"><Icon name="shield" size={16} />Security & sessions</Link>
              <div className="menu-sep" />
              <button className="menu-item" role="menuitem" onClick={async () => { close(); await logout(); navigate('/login', { replace: true }); }}>
                <Icon name="logout" size={16} />Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

function NotificationsPopover({ onClose }: { onClose: () => void }) {
  const q = useQuery({ queryKey: ['os', 'notifications', 'peek'], queryFn: () => api.notifications.list({ page_size: 6 }) });
  return (
    <div className="popover" style={{ width: 360, padding: 0 }} role="dialog" aria-label="Recent notifications">
      <div className="card__head"><h2>Notifications</h2><Link to="/notifications" onClick={onClose} className="small">View all</Link></div>
      {q.isPending ? <div className="loader"><span className="muted small">Loading…</span></div> : q.data?.results.length ? (
        <ul className="list">
          {q.data.results.map((n) => (
            <li key={n.id}>
              <Link to={n.path || '/notifications'} className={`list-row ${n.read ? '' : 'list-row--unread'}`} onClick={() => { if (!n.read) void api.notifications.read(n.id); onClose(); }}>
                <span className={`dot ${n.read ? 'dot--off' : n.priority !== 'normal' ? `dot--${n.priority}` : ''}`} />
                <span className="list-row__main"><span className="list-row__title" style={{ display: 'block' }}>{n.title}</span><span className="list-row__sub" style={{ display: 'block' }}>{n.body || n.typeLabel}</span></span>
                <span className="list-row__aside">{relative(n.createdAt)}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : <p className="muted small" style={{ padding: 16 }}>You’re all caught up.</p>}
    </div>
  );
}
