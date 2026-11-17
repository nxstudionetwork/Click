import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { Icon, Logo, type IconName } from '@click/ui';
import type { Partner, PartnerHome, PartnerMode } from '@click/api';
import { iconFor } from '../config/visuals';
import { useHome } from '../features/home/queries';
import { usePartnerSession } from '../session/PartnerSession';
import { initials } from './PartnerCard';

/** The Work tab per workspace noun (server-decided by the partner's type; the app only labels it). */
export const WORK_LABEL: Record<string, { label: string; title: string; icon: IconName }> = {
  ride: { label: 'Rides', title: 'Rides', icon: 'ride' },
  order: { label: 'Orders', title: 'Orders', icon: 'receipt' },
  booking: { label: 'Bookings', title: 'Shows & bookings', icon: 'ticket' },
  delivery: { label: 'Deliveries', title: 'Deliveries', icon: 'parcel' },
  stay: { label: 'Stays', title: 'Stays & bookings', icon: 'hotel' },
  job: { label: 'Jobs', title: 'Jobs', icon: 'wrench' },
  event: { label: 'Events', title: 'Events', icon: 'gift' },
  visit: { label: 'Visits', title: 'Visits & entry', icon: 'compass' },
  trip: { label: 'Trips', title: 'Trips & runs', icon: 'bus' },
};

type NavItem = { to: string; label: string; icon: IconName; tab: boolean };

/** Restaurant mode: Home | Orders | Kitchen | Menu | More on the phone bar; the desktop rail lists every tool. */
const RESTAURANT_NAV: NavItem[] = [
  { to: '/home', label: 'Home', icon: 'home', tab: true },
  { to: '/restaurant/orders', label: 'Orders', icon: 'receipt', tab: true },
  { to: '/restaurant/kitchen', label: 'Kitchen', icon: 'food', tab: true },
  { to: '/restaurant/menu', label: 'Menu', icon: 'book', tab: true },
  { to: '/restaurant/offers', label: 'Offers', icon: 'tag', tab: false },
  { to: '/restaurant/insights', label: 'Insights', icon: 'chart', tab: false },
  { to: '/earnings', label: 'Earnings', icon: 'wallet', tab: false },
  { to: '/notifications', label: 'Alerts', icon: 'bell', tab: false },
  { to: '/more', label: 'More', icon: 'menu', tab: true },
];

/**
 * Navigation follows the partner's server-derived mode. Home is common; Work and Earnings appear only when the
 * partner's workspace is live (never as dead links). `tab` items fit the phone bar; the rail shows the rest too.
 */
export function navItems(home: PartnerHome | undefined, mode?: PartnerMode): NavItem[] {
  // Restaurant tools stay in place while Home loads; they hide only when the restaurant isn't connected yet.
  if (mode === 'restaurant' && (!home || home.workspace.state === 'live')) return RESTAURANT_NAV;
  const items: NavItem[] = [{ to: '/home', label: 'Home', icon: 'home', tab: true }];
  if (home?.workspace.state === 'live') {
    const work = WORK_LABEL[home.workspace.workNoun] ?? { label: 'Work', icon: 'briefcase' as IconName };
    items.push({ to: '/work', label: work.label, icon: work.icon, tab: true }, { to: '/earnings', label: 'Earnings', icon: 'wallet', tab: true });
  }
  items.push({ to: '/notifications', label: 'Alerts', icon: 'bell', tab: true });
  return items;
}

function Verified({ partner }: { partner: Partner }) {
  if (partner.isVerified) return <span className="pid__verified"><Icon name="shield" size={13} /> Verified</span>;
  return <span className="pid__pending"><Icon name="clock" size={13} /> {partner.statusLabel}</span>;
}

function AccountMenu({ partner }: { partner: Partner }) {
  const { logout } = usePartnerSession();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', close); };
  }, [open]);
  return (
    <div className="menu" ref={ref}>
      <button type="button" className="avatar-btn" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}
        aria-label="Account and settings">
        {initials(partner.businessName)}
      </button>
      {open && (
        <div className="menu__list" role="menu">
          <div className="menu__who">
            <strong>{partner.businessName}</strong>
            <span className="mono small">{partner.partnerCode}</span>
          </div>
          <Link role="menuitem" to="/card" className="menu__item"><Icon name="card" size={18} /> Partner card</Link>
          <Link role="menuitem" to="/notifications" className="menu__item"><Icon name="bell" size={18} /> Notifications</Link>
          <button role="menuitem" type="button" className="menu__item" onClick={() => void logout()}><Icon name="logout" size={18} /> Sign out</button>
        </div>
      )}
    </div>
  );
}

function HelpDialog({ open, onClose, home, partner }: { open: boolean; onClose: () => void; home?: PartnerHome; partner: Partner }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (open && d && !d.open) d.showModal?.();
    if (!open && d?.open) d.close();
  }, [open]);
  const a = home?.availability;
  return (
    <dialog ref={ref} className="dialog" aria-labelledby="help-t" onCancel={(e) => { e.preventDefault(); onClose(); }}
      onClick={(e) => { if (e.target === ref.current) onClose(); }}>
      {open && (
        <div className="dialog__body">
          <h2 id="help-t">How Partner Home works</h2>
          <ul className="help">
            {a && <li><strong>Status: {a.onLabel} / {a.offLabel}.</strong> {a.blockedReason || 'Switch it from Home. Click saves it immediately and customers see the change.'}</li>}
            <li><strong>Action required</strong> lists work waiting for your decision. Accept, reject or update it there; nothing changes until Click confirms it.</li>
            <li><strong>Today’s overview</strong> and earnings come from your completed work on Click, counted in India time.</li>
            <li>Home refreshes every few seconds while it’s open. Notifications collect new work and account updates.</li>
            <li>Your Partner ID <span className="mono">{partner.partnerCode}</span> identifies you to Click support. Keep your Partner card handy.</li>
          </ul>
          <div className="dialog__actions"><button type="button" className="btn btn--primary" onClick={onClose}>Got it</button></div>
        </div>
      )}
    </dialog>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { partner: state } = usePartnerSession();
  const partner = state.state?.partner;
  const home = useHome();
  const [help, setHelp] = useState(false);
  if (!partner) return null;
  const items = navItems(home.data, partner.mode);
  const unread = home.data?.notifications.unread ?? 0;

  return (
    <div className="shell">
      <header className="pbar">
        <Link to="/home" className="pid" aria-label={`${partner.businessName}, Partner Home`}>
          <span className="pid__logo" aria-hidden="true">
            <Icon name={iconFor(partner.category.icon)} size={22} />
          </span>
          <span className="pid__text">
            <span className="pid__name">{partner.businessName}</span>
            <span className="pid__meta">
              <span className="mono">{partner.partnerCode}</span><span className="pid__cat"><span aria-hidden="true"> · </span>{partner.category.name}</span>
              <span aria-hidden="true"> · </span><Verified partner={partner} />
            </span>
          </span>
        </Link>
        <div className="pbar__actions">
          <Link to="/notifications" className="icon-btn pbar__bell" aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}>
            <Icon name="bell" size={20} />
            {unread > 0 && <span className="badge" aria-hidden="true">{unread > 99 ? '99+' : unread}</span>}
          </Link>
          <button type="button" className="icon-btn" aria-label="Help" onClick={() => setHelp(true)}><Icon name="help" size={20} /></button>
          <AccountMenu partner={partner} />
        </div>
      </header>

      <div className="shell__body">
        <nav className="rail" aria-label="Partner navigation">
          <div className="rail__brand"><Logo product="Partner" size={24} /></div>
          {items.map((i) => (
            <NavLink key={i.to} to={i.to} className="rail__item">
              <Icon name={i.icon} size={20} /><span>{i.label}</span>
              {i.to === '/notifications' && unread > 0 && <span className="badge badge--inline" aria-label={`${unread} unread`}>{unread}</span>}
            </NavLink>
          ))}
        </nav>
        <main id="main" className="shell__main">{children}</main>
      </div>

      <nav className="tabbar" aria-label="Partner navigation">
        {items.filter((i) => i.tab).map((i) => (
          <NavLink key={i.to} to={i.to} className="tabbar__item">
            <span className="tabbar__icon"><Icon name={i.icon} size={22} />
              {i.to === '/notifications' && unread > 0 && <span className="badge" aria-hidden="true">{unread > 9 ? '9+' : unread}</span>}
            </span>
            <span>{i.label}</span>
          </NavLink>
        ))}
      </nav>
      <HelpDialog open={help} onClose={() => setHelp(false)} home={home.data} partner={partner} />
    </div>
  );
}
