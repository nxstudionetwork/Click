import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react';
import { Button } from '@click/ui';
import { Sheet } from './Sheet';

interface ConfirmOptions { title: string; message?: string; confirmLabel?: string; cancelLabel?: string; danger?: boolean }
type Confirm = (o: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<Confirm>(async () => false);

/** In-app confirmation dialog (replaces the browser's confirm()). `await confirm({...})` resolves true/false. */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [opts, setOpts] = useState<ConfirmOptions | null>(null);
  const resolver = useRef<(v: boolean) => void>(() => {});
  const confirm = useCallback<Confirm>((o) => new Promise((resolve) => { resolver.current = resolve; setOpts(o); }), []);
  const done = (v: boolean) => { resolver.current(v); setOpts(null); };
  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Sheet open={!!opts} onClose={() => done(false)} label={opts?.title ?? 'Confirm'}>
        {opts && (
          <div className="psheet" role="alertdialog" aria-labelledby="confirm-h" aria-describedby={opts.message ? 'confirm-d' : undefined}>
            <h2 id="confirm-h">{opts.title}</h2>
            {opts.message && <p id="confirm-d" className="muted">{opts.message}</p>}
            <div className="row">
              <Button variant="outline" onClick={() => done(false)}>{opts.cancelLabel ?? 'Cancel'}</Button>
              <Button variant={opts.danger ? 'danger' : 'primary'} onClick={() => done(true)}>{opts.confirmLabel ?? 'Continue'}</Button>
            </div>
          </div>
        )}
      </Sheet>
    </ConfirmContext.Provider>
  );
}

export const useConfirm = () => useContext(ConfirmContext);
