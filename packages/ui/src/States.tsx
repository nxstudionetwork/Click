import type { ReactNode } from 'react';
import { Button } from './Button';
import { Icon, type IconName } from './Icon';

export function EmptyState({ icon = 'search', title, message, action }: { icon?: IconName; title: string; message?: string; action?: ReactNode }) {
  return (
    <div className="state" role="status">
      <div className="state__icon"><Icon name={icon} /></div>
      <h3>{title}</h3>
      {message && <p>{message}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : 'Something went wrong.';
  return (
    <div className="state state--error" role="alert">
      <div className="state__icon"><Icon name="alert" /></div>
      <h3>We couldn’t load this</h3>
      <p>{message}</p>
      {onRetry && <Button variant="outline" onClick={onRetry}>Try again</Button>}
    </div>
  );
}

export function Skeleton({ width = '100%', height = 16, radius }: { width?: number | string; height?: number | string; radius?: number }) {
  return <div className="skeleton" style={{ width, height, borderRadius: radius }} aria-hidden="true" />;
}
