import { formatMoney } from '../../lib/format';
import { useWallet } from './useWallet';

/** "Pay with Click Wallet" choice for any checkout. Disabled (with reason) when the balance can't cover the total. */
export function WalletOption({ total, currency, checked, onSelect }: { total: string; currency: string; checked: boolean; onSelect: () => void }) {
  const wallet = useWallet();
  const balance = Number(wallet.data?.balance ?? 0);
  const enough = balance >= Number(total);
  return (
    <label className="option" style={!enough ? { opacity: 0.6, cursor: 'not-allowed' } : undefined}>
      <input type="radio" name="payment" checked={checked} disabled={!enough || wallet.isPending} onChange={onSelect} />
      <div>
        <strong>Click Wallet</strong>
        <div className="muted small">
          {wallet.isPending ? 'Checking balance…' : wallet.isError ? 'Wallet unavailable right now'
            : `Balance ${formatMoney(balance, currency)}${enough ? ' · paid instantly' : ' · not enough for this payment'}`}
        </div>
      </div>
    </label>
  );
}
