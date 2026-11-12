import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import { renderWithProviders } from '../test/utils';

const info = {
  id: 'a1', slug: 'charminar', name: 'Charminar', kind: 'monument', kindLabel: 'Monument', group: 'tourist', groupLabel: 'Tourist spots', city: 'Hyderabad',
  region: 'Telangana', area: 'Old City', tagline: '', deity: '', accent: '#57534e', imageUrl: null, rating: null, bookable: false, verified: false, instant: false,
  freeCancellation: false, fromPrice: null, bookingTypes: [], nextAvailable: null, officialSource: 'Entry tickets are sold by the Archaeological Survey of India.',
  durationMinutes: null, familyFriendly: false, kidsFriendly: false, setting: 'outdoor', distanceKm: null, favoriteId: null, recentBookings: 0,
  description: 'The four-minaret monument.', highlights: [], facilities: [], accessibility: [], rules: [], dressCode: '', prohibited: [], ageNote: '', opening: null,
  address: '', latitude: 17.36, longitude: 78.47, faqs: [], officialUrl: null, provider: null, images: [], policy: 'Non-refundable.', offerings: [], reviews: [], related: [],
};
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'anonymous', user: null }) }));
vi.mock('../lib/api', () => ({ api: { bookings: { attraction: vi.fn().mockResolvedValue(info), availability: vi.fn() } } }));
const { AttractionPage } = await import('./AttractionPage');

describe('Attraction page', () => {
  it('an information-only place is never presented as bookable: no prices, slots or Book button, and says where it is booked', async () => {
    renderWithProviders(<Routes><Route path="/bookings/places/:slug" element={<AttractionPage />} /></Routes>, { route: '/bookings/places/charminar' });
    expect(await screen.findByRole('heading', { name: 'Charminar' })).toBeInTheDocument();
    expect(screen.getByText('Information available')).toBeInTheDocument();
    expect(screen.getByText('Not bookable through Click.')).toBeInTheDocument();
    expect(screen.getByText(/Archaeological Survey of India/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /continue|book/i })).toBeNull();
    expect(screen.queryByText(/₹/)).toBeNull();
    expect(screen.getByRole('img', { name: /no photos yet/ })).toBeInTheDocument();
  });
});
