import { useEffect, useState } from 'react';
import QRCode from 'qrcode';
import type { User } from '@click/api';
import { maskPhone } from '../auth/phone/countries';
import { Icon } from '../components/ui';

/** What the QR and the shared image contain: name + Click ID only (no phone, email or address). */
export const shareText = (u: User) => `${u.fullName} is on Click · Click ID ${u.customerCode}`;
const qrPayload = (u: User) => `CLICK-ID:${u.customerCode}`;
const memberSince = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' });
const maskEmail = (e: string) => e.replace(/^(.{2})[^@]*(@.*)$/, (_, a, b) => `${a}•••${b}`);

export function CustomerCard({ user }: { user: User }) {
  const [qr, setQr] = useState('');
  useEffect(() => { QRCode.toDataURL(qrPayload(user), { margin: 1, width: 240, color: { dark: '#14121f', light: '#ffffff' } }).then(setQr).catch(() => setQr('')); }, [user]);
  const initial = (user.fullName || user.email).trim()[0]!.toUpperCase();
  return (
    <article className="ccard" aria-label="Your Click customer card">
      <div className="ccard__glow" aria-hidden="true" />
      <header className="ccard__head">
        <span className="ccard__brand"><svg viewBox="0 0 32 32" width="26" height="26" aria-hidden="true"><rect width="32" height="32" rx="9" fill="#fff" /><circle cx="16" cy="16" r="7.5" fill="none" stroke="var(--c-brand)" strokeWidth="3" /><circle cx="16" cy="16" r="2.6" fill="var(--c-accent)" /></svg>click</span>
        <span className="ccard__member">Member since {memberSince(user.createdAt)}</span>
      </header>
      <div className="ccard__body">
        <div className="ccard__avatar">{user.avatarUrl ? <img src={user.avatarUrl} alt="" /> : <span>{initial}</span>}</div>
        <div style={{ minWidth: 0 }}>
          <h2 className="ccard__name">{user.fullName}{user.phoneVerified && <span className="ccard__verified" title="Phone verified"><Icon name="check" size={14} /></span>}</h2>
          <div className="ccard__id"><span>Click ID</span><strong>{user.customerCode}</strong></div>
        </div>
      </div>
      <footer className="ccard__foot">
        <div className="ccard__meta">
          <span><Icon name="shield" size={14} /> {user.phone ? maskPhone(user.phone) : 'Phone not added'}</span>
          <span>{maskEmail(user.email)}</span>
        </div>
        {qr && <img className="ccard__qr" src={qr} alt={`QR code for Click ID ${user.customerCode}`} />}
      </footer>
    </article>
  );
}

/** Renders the shareable version of the card (no phone/email) to a PNG blob. */
export async function renderCardPng(user: User): Promise<Blob> {
  const W = 1080, H = 640, c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d')!;
  const bg = g.createLinearGradient(0, 0, W, H);
  bg.addColorStop(0, '#2d1a9e'); bg.addColorStop(0.55, '#5b3df5'); bg.addColorStop(1, '#14c8a0');
  g.fillStyle = bg; roundRect(g, 0, 0, W, H, 48); g.fill();
  g.fillStyle = 'rgba(255,255,255,0.08)'; g.beginPath(); g.arc(W - 120, 90, 230, 0, Math.PI * 2); g.fill();
  g.fillStyle = '#fff'; g.font = '800 56px system-ui, sans-serif'; g.fillText('click', 72, 112);
  g.font = '600 28px system-ui, sans-serif'; g.globalAlpha = 0.85; g.fillText(`Member since ${memberSince(user.createdAt)}`, 72, 160); g.globalAlpha = 1;
  g.font = '800 64px system-ui, sans-serif'; g.fillText(fit(g, user.fullName, 620), 72, 400);
  g.font = '600 28px system-ui, sans-serif'; g.globalAlpha = 0.85; g.fillText('CLICK ID', 72, 470); g.globalAlpha = 1;
  g.font = '700 48px ui-monospace, Menlo, monospace'; g.fillText(user.customerCode ?? '', 72, 530);
  const qr = await QRCode.toDataURL(qrPayload(user), { margin: 1, width: 300 });
  const img = await new Promise<HTMLImageElement>((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = qr; });
  g.fillStyle = '#fff'; roundRect(g, W - 372, H - 372, 300, 300, 24); g.fill();
  g.drawImage(img, W - 357, H - 357, 270, 270);
  return new Promise((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error('render failed'))), 'image/png'));
}

function roundRect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
}
function fit(g: CanvasRenderingContext2D, text: string, max: number) {
  let t = text;
  while (g.measureText(t).width > max && t.length > 3) t = t.slice(0, -2);
  return t === text ? t : `${t}…`;
}
