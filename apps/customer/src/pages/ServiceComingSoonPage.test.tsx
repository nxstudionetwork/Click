import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SERVICES } from '../config/services';
import { renderWithProviders } from '../test/utils';
import { ServiceComingSoonPage } from './ServiceComingSoonPage';

describe('ServiceComingSoonPage', () => {
  it.each(SERVICES.filter((s) => s.status === 'soon').map((s) => s.id))('%s is honest: not live, nothing bookable', (id) => {
    renderWithProviders(<ServiceComingSoonPage serviceId={id} />);
    expect(screen.getByText('Not live yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /book|request|confirm/i })).toBeNull();
  });
});
