import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon, Sheet } from '../ui';

/** AI entry point: choose Voice (talk to Buddy) or Go (open Buddy). */
export function BuddyLauncher() {
  const [open, setOpen] = useState(false);
  const [voiceNote, setVoiceNote] = useState(false);
  const navigate = useNavigate();
  const close = () => { setOpen(false); setVoiceNote(false); };
  return (
    <>
      <button className="icon-btn buddy-btn" aria-label="Buddy, Click AI" onClick={() => setOpen(true)}><Icon name="sparkle" /></button>
      <Sheet open={open} onClose={close} label="Buddy">
        <div className="stack" style={{ padding: 'var(--s-6)' }}>
          <div className="spread"><h2>Buddy</h2><button className="icon-btn" aria-label="Close" onClick={close}><Icon name="close" /></button></div>
          <p className="muted">Your Click assistant for finding, planning and getting things done.</p>
          <div className="buddy-choice">
            <button className="buddy-choice__opt" onClick={() => setVoiceNote(true)}>
              <span className="buddy-choice__icon"><Icon name="mic" /></span>
              <strong>Voice</strong><span className="small muted">Talk to Buddy</span>
            </button>
            <button className="buddy-choice__opt buddy-choice__opt--go" onClick={() => { close(); navigate('/buddy'); }}>
              <span className="buddy-choice__icon"><Icon name="sparkle" /></span>
              <strong>Go</strong><span className="small">Open Buddy</span>
            </button>
          </div>
          {voiceNote && <p className="badge badge--warning" role="status" style={{ whiteSpace: 'normal', padding: '8px 12px' }}>Voice conversations are coming soon. Tap Go to chat with Buddy now.</p>}
        </div>
      </Sheet>
    </>
  );
}
