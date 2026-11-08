import { useState } from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';
import { Button, Icon, Logo, useToast } from '@click/ui';
import { cardData, PartnerCard, type CardData } from '../components/PartnerCard';
import { renderCardImage } from '../components/cardImage';
import { usePartnerSession } from '../session/PartnerSession';

const fileName = (d: CardData) => `click-partner-${d.partnerCode}.png`;
const shareText = (d: CardData) => `${d.businessName} is a Click Partner (${d.categoryName}). Partner ID: ${d.partnerCode}`;

export function CardPage() {
  const { partner } = usePartnerSession();
  const location = useLocation();
  const toast = useToast();
  const [busy, setBusy] = useState<'save' | 'share' | null>(null);
  const data = partner.state?.partner ? cardData(partner.state.partner) : null;
  if (!data) return <Navigate to="/" replace />;
  const justCreated = (location.state as { justCreated?: boolean } | null)?.justCreated;

  async function save() {
    setBusy('save');
    try {
      const blob = await renderCardImage(data!);
      const url = URL.createObjectURL(blob);
      const a = Object.assign(document.createElement('a'), { href: url, download: fileName(data!) });
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      toast('Partner card saved.');
    } catch {
      toast('We couldn’t save the card on this device.', 'error');
    } finally {
      setBusy(null);
    }
  }

  async function share() {
    setBusy('share');
    try {
      const text = shareText(data!);
      if (navigator.share) {
        const file = new File([await renderCardImage(data!)], fileName(data!), { type: 'image/png' });
        const payload: ShareData = navigator.canShare?.({ files: [file] }) ? { files: [file], title: 'Click Partner', text } : { title: 'Click Partner', text };
        await navigator.share(payload);
      } else if (navigator.clipboard) {
        await navigator.clipboard.writeText(text);
        toast('Card details copied. Paste them anywhere to share.');
      } else {
        toast('Sharing isn’t supported on this device. Use Save instead.', 'error');
      }
    } catch (err) {
      if ((err as Error)?.name !== 'AbortError') toast('We couldn’t share right now.', 'error');
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="card-page">
      <header className="card-page__bar"><Logo tone="dark" product="Partner" size={26} /></header>
      <main id="main" className="card-page__main">
        <div className="card-page__head">
          {justCreated && <p className="eyebrow eyebrow--on-dark"><Icon name="check" size={14} /> Partner ID created</p>}
          <h1>{justCreated ? 'Welcome to Click Partner' : 'Your Partner card'}</h1>
          <p>Your permanent Click Partner ID is <strong>{data.partnerCode}</strong>. It stays the same even if your phone or email changes.</p>
        </div>
        <div className="card-page__card"><PartnerCard data={data} /></div>
        <div className="card-page__actions">
          <Button variant="secondary" onClick={() => void save()} loading={busy === 'save'} disabled={!!busy}><Icon name="download" size={18} /> Save</Button>
          <Button variant="secondary" onClick={() => void share()} loading={busy === 'share'} disabled={!!busy}><Icon name="share" size={18} /> Share</Button>
        </div>
        <p className="card-page__note small">Your card shows only your name, Partner ID, category and status. Your phone, address and documents are never included.</p>
        <Link to="/home" className="btn btn--primary btn--block card-page__continue">Continue to Partner Home <Icon name="right" size={18} /></Link>
      </main>
    </div>
  );
}
