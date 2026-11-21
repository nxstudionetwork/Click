/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Shared shell for Business OS module workspaces: the module's own navigation comes from the server (only what the
 * person may use), plus small helpers every module screen needs (titles, money, CSV download, action buttons).
 */
import type { ReactNode } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { OSModuleApi } from '@click/api';
import { Button, Icon, useToast, type IconName } from '@click/ui';
import { apiMessage } from '../lib/api';
import { fmtMoney } from '../lib/format';
import { LoadingRows, PageHeader, QueryError } from './ui';

export function ModuleShell({ api, label, root, icon = 'home' }: { api: OSModuleApi; label: string; root: string; icon?: IconName }) {
  const nav = useQuery({ queryKey: ['os', 'nav', api.base], queryFn: api.nav, staleTime: 120_000 });
  return (
    <div className="module-layout">
      <nav className="sidenav" aria-label={label}>
        {nav.isPending ? <LoadingRows rows={6} /> : nav.error ? <QueryError error={nav.error} /> : nav.data.sections.map((sec) => (
          <div key={sec.key} style={{ display: 'contents' }}>
            <div className="sidenav__label">{sec.label}</div>
            {sec.items.map((i) => (
              <NavLink key={i.key} to={i.path.split('?')[0]!} end={i.path === root}>
                {i.path === root && <Icon name={icon} size={16} />}{i.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      <div style={{ minWidth: 0 }}><Outlet /></div>
    </div>
  );
}

export function ModuleTitle({ module, root, title, desc, actions }: { module: string; root: string; title: string; desc?: ReactNode; actions?: ReactNode }) {
  return <PageHeader title={title} description={desc as string} crumbs={[{ label: module, to: root }, { label: title }]} actions={actions} />;
}

export const money = (v: any, cur?: string) => (v === null || v === undefined || v === '' ? '—' : fmtMoney(v, cur ?? 'INR'));

/** Runs a POST/PATCH action, toasts the outcome and refreshes the given query keys. */
export function useAction<T = any>(fn: (vars: T) => Promise<unknown>, refresh: unknown[][], ok = 'Done') {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => { toast(ok); refresh.forEach((k) => void qc.invalidateQueries({ queryKey: k })); },
    onError: (e) => toast(apiMessage(e), 'error'),
  });
}

export function DownloadButton({ api, path, query = {}, filename, label = 'Export CSV' }: {
  api: OSModuleApi; path: string; query?: Record<string, any>; filename: string; label?: string;
}) {
  const toast = useToast();
  return (
    <Button variant="outline" onClick={async () => {
      try {
        const blob = await api.blob(path, { ...query, export: 'csv' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        a.click();
      } catch (e) { toast(apiMessage(e), 'error'); }
    }}><Icon name="download" size={16} />{label}</Button>
  );
}

export function Kpis({ items }: { items: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'alert' | 'good'; to?: string }[] }) {
  return (
    <div className="stat-grid">
      {items.map((s) => {
        const body = (<><span className="stat__label">{s.label}</span>
          <strong className={`stat__value ${s.tone ? `stat__value--${s.tone}` : ''}`}>{s.value ?? '—'}</strong>
          {s.hint && <span className="stat__hint">{s.hint}</span>}</>);
        return s.to ? <NavLink key={s.label} to={s.to} className="stat stat--link">{body}</NavLink> : <div key={s.label} className="stat">{body}</div>;
      })}
    </div>
  );
}
