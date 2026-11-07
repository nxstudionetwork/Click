export function Logo() {
  return (
    <span className="logo" aria-label="Click">
      <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="9" fill="var(--c-brand)" />
        <circle cx="16" cy="16" r="7.5" fill="none" stroke="#fff" strokeWidth="3" />
        <circle cx="16" cy="16" r="2.6" fill="var(--c-accent)" />
      </svg>
      click
    </span>
  );
}
