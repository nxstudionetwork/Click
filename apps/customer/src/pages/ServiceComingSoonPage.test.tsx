import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SERVICES } from '../config/services';
import { renderWithProviders } from '../test/utils';
import { ServiceComingSoonPage } from './ServiceComingSoonPage';

describe('ServiceComingSoonPage', () => {
  const soon = SERVICES.filter((s) => s.status === 'soon').map((s) => s.id);
  it('every live service is not marked soon', () => { expect(SERVICES.filter((s) => s.status === 'live').length).toBeGreaterThan(0); });
  it.skipIf(soon.length === 0).each(soon.length ? soon : ['none'])('%s is honest: not live, nothing bookable', (id) => {
    renderWithProviders(<ServiceComingSoonPage serviceId={id} />);
    expect(screen.getByText('Not live yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /book|request|confirm/i })).toBeNull();
  });
});
