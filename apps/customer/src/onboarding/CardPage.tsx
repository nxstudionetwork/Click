import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { Button, Icon, useToast } from '../components/ui';
import { AuthLayout } from './AuthLayout';
import { CustomerCard, renderCardPng, shareText } from './CustomerCard';

/** Shown right after signup (/welcome/card) and from Account (/account/card). */
export function CardPage({ onboardingStep = true }: { onboardingStep?: boolean }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [busy, setBusy] = useState<'save' | 'share' | null>(null);
  if (!user?.customerCode) return null;
  const fileName = `click-id-${user.customerCode}.png`;

  async function save() {
    setBusy('save');
    try {
      const blob = await renderCardPng(user!);
      const url = URL.createObjectURL(blob);
      const a = Object.assign(document.createElement('a'), { href: url, download: fileName });
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      toast('Card saved to your device');
    } catch { toast('Couldn’t save the card. Please try again.', 'error'); } finally { setBusy(null); }
  }

  async function share() {
    setBusy('share');
    try {
      const text = shareText(user!);
      const blob = await renderCardPng(user!);
      const file = new File([blob], fileName, { type: 'image/png' });
      if (navigator.canShare?.({ files: [file] })) await navigator.share({ files: [file], title: 'My Click ID', text });
      else if (navigator.share) await navigator.share({ title: 'My Click ID', text });
      else { await navigator.clipboard.writeText(text); toast('Click ID copied to clipboard'); }
    } catch (e) {
      if ((e as Error).name !== 'AbortError') toast('Sharing isn’t available here. Use Save instead.', 'error');
    } finally { setBusy(null); }
  }

  const body = (
    <div className="stack card-reveal">
      <div className="auth-intro">
        <h1>{onboardingStep ? 'You’re in!' : 'Your Click card'}</h1>
        <p>{onboardingStep ? 'This is your Click identity. Your Click ID stays the same even if your phone or email changes.' : 'Your permanent Click identity.'}</p>
      </div>
      <CustomerCard user={user} />
      <div className="row card-actions">
        <Button variant="outline" onClick={save} loading={busy === 'save'}><Icon name="plus" size={18} /> Save</Button>
        <Button variant="outline" onClick={share} loading={busy === 'share'}><Icon name="send" size={18} /> Share</Button>
      </div>
      <p className="small muted">Saving or sharing includes only your name, Click ID and QR code. Never your phone or email.</p>
      {onboardingStep ? <Button block className="btn--lg" onClick={() => navigate('/', { replace: true })}>Start exploring Click</Button>
        : <Link to="/account" className="btn btn--ghost">Back to account</Link>}
    </div>
  );
  return onboardingStep ? <AuthLayout visual={false}>{body}</AuthLayout> : <div style={{ maxWidth: 560, margin: '0 auto' }}>{body}</div>;
}
