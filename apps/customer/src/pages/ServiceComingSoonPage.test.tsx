import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SERVICES } from '../config/services';
import { renderWithProviders } from '../test/utils';
import { ServiceComingSoonPage } from './ServiceComingSoonPage';

describe('ServiceComingSoonPage', () => {
  it.each(SERVICES.filter((s) => s.status === 'soon').map((s) => s.id))('%s shows an honest not-live state with no bookable content', (id) => {
    renderWithProviders(<ServiceComingSoonPage serviceId={id} />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('is coming to Click');
    expect(screen.queryByRole('button', { name: /book|request/i })).toBeNull();
  });
});
