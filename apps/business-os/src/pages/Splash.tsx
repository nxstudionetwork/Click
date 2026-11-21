export function Splash({ status }: { status: string }) {
  return (
    <div className="splash" role="status" aria-live="polite">
      <div className="splash__inner">
        <svg width="56" height="56" viewBox="0 0 32 32" aria-hidden="true">
          <rect width="32" height="32" rx="9" fill="#5B3DF5" />
          <circle cx="16" cy="16" r="7.5" fill="none" stroke="#fff" strokeWidth="3" />
          <circle cx="16" cy="16" r="2.6" fill="#14C8A0" />
        </svg>
        <div className="splash__word">CLICK</div>
        <div className="splash__sub">Business OS</div>
        <div className="splash__bar" aria-hidden="true"><span /></div>
        <div className="splash__status">{status}</div>
      </div>
    </div>
  );
}
