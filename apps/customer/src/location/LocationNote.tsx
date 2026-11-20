import { Icon } from '../components/ui';
import { useDeliveryLocation } from './LocationProvider';
import { formatArea } from './LocationSelector';

/**
 * Read-only reminder of the app-wide location on service pages. The location is chosen once on Home and used
 * everywhere; checkout confirms it and lets the customer change it for that order.
 */
export function LocationNote({ verb = 'Showing results for' }: { verb?: string }) {
  const { selected } = useDeliveryLocation();
  if (!selected) return null;
  return (
    <p className="loc-note">
      <Icon name="pin" size={14} />
      <span>{verb} <strong>{selected.label}</strong> · {formatArea(selected)}</span>
    </p>
  );
}
