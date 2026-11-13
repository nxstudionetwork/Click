import { useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthProvider';
import { api } from '../../lib/api';
import { Icon, Sheet } from '../ui';

/**
 * The header Buddy icon. It never jumps straight into a chat: it offers the two Buddy experiences, which share the
 * same intelligence, conversations and action layer —
 *   MAN  the visual, conversational workspace (/buddy)
 *   GO   voice first, hands-free (/buddy/go)
 */
export function BuddySelector() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const { status } = useAuth();
  const authed = status === 'authenticated';
  const go = (mode: 'man' | 'go') => {
    if (authed) api.buddy.track(mode === 'man' ? 'mode_man' : 'mode_go');
    setOpen(false);
    navigate(mode === 'man' ? '/buddy' : '/buddy/go');
  };
  return (
    <>
      <button className="icon-btn buddy-btn" aria-label="Buddy, your Click. assistant" aria-haspopup="dialog"
        onClick={() => { setOpen(true); if (authed) api.buddy.track('opened'); }}>
        <Icon name="sparkle" />
      </button>
      {/* Portalled: the header's backdrop blur would otherwise trap a fixed-position sheet inside the header. */}
      {createPortal(<Sheet open={open} onClose={() => setOpen(false)} label="Choose Buddy">
        <div className="bd-choose" data-theme="buddy">
          <div className="bd-choose__head">
            <span className="bd-orb bd-orb--sm" aria-hidden="true" />
            <div><h2>Buddy</h2><span className="small bd-muted">Your Click. intelligence — choose how to talk.</span></div>
            <button type="button" className="bd-icon" aria-label="Close" onClick={() => setOpen(false)}><Icon name="close" size={18} /></button>
          </div>
          <div className="bd-modes">
            <button type="button" className="bd-mode bd-mode--man" onClick={() => go('man')}>
              <span className="bd-mode__icon"><Icon name="sparkle" size={26} /></span>
              <span className="bd-mode__name">Man</span>
              <span className="bd-mode__desc">Talk, ask, search, plan and control Click.</span>
              <span className="bd-mode__go small">Open workspace <Icon name="right" size={12} /></span>
            </button>
            <button type="button" className="bd-mode bd-mode--go" onClick={() => go('go')}>
              <span className="bd-mode__icon"><Icon name="mic" size={26} /></span>
              <span className="bd-mode__name">Go</span>
              <span className="bd-mode__desc">Just speak. Tell Click what you need.</span>
              <span className="bd-mode__go small">Start talking <Icon name="right" size={12} /></span>
            </button>
          </div>
          <p className="small bd-muted bd-choose__note"><Icon name="shield" size={12} /> Buddy asks before anything important and never pays for you.</p>
        </div>
      </Sheet>, document.body)}
    </>
  );
}
