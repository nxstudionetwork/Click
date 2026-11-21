import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import { renderWithProviders } from '../test/utils';

const quote = {
  id: 'q1', version: 1, items: [{ label: 'Decor', amount: '48000.00', optional: false }, { label: 'Photographer', amount: '18000.00', optional: true }],
  amount: '48000.00', tax: '8640.00', total: '56640.00', durationHours: 5, teamSize: 12, terms: 'Venue not included', notes: '', validUntil: '2099-01-01',
  expired: false, status: 'pending', statusLabel: 'Waiting for you', customerNote: '', createdAt: '2030-01-01T10:00:00Z',
};
const enquiry = {
  id: 'e1', status: 'quoted', statusLabel: 'Quote received', message: '', createdAt: '2030-01-01T09:00:00Z',
  provider: { id: 'p1', name: 'Kalpavruksha Celebrations', kind: 'team', accent: '#f59e0b', logoUrl: '', verified: true, rating: { average: '4.7', count: 9 } },
  package: null, quotes: [quote], messages: [], bookingId: null,
};
const plan = {
  id: 'pl1', number: 'EVP-TEST0001', title: 'Parents’ 25th anniversary', status: 'planning', statusLabel: 'Planning',
  eventType: { slug: 'anniversary', name: 'Anniversary', icon: 'heart', accent: '#e879f9', summary: '', group: 'personal', suggestedServices: [] },
  date: '2099-02-14', dateFlexible: false, dateNote: '', startTime: null, guests: 60, address: { line1: '1 Test Road', line2: 'Indiranagar' },
  createdAt: '2030-01-01T09:00:00Z', quotesWaiting: 1, bookings: 0, budget: { min: '60000.00', max: '150000.00', flexible: false },
  services: [{ slug: 'decoration', name: 'Decoration', icon: 'gift', group: 'decor' }], requirements: 'Warm, elegant decor', needsVenue: false, attachments: [],
  checklist: [{ id: 'c1', label: 'Confirm decoration', done: false, auto: false, service: 'Decoration', custom: false }], progress: { done: 0, total: 1 },
  enquiries: [enquiry], bookingList: [],
};
const enquiryAct = vi.fn().mockResolvedValue({ ...enquiry, status: 'revision', statusLabel: 'Changes requested', quotes: [{ ...quote, status: 'changes', customerNote: 'Add a cake' }] });
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'authenticated', user: {} }) }));
vi.mock('../lib/api', () => ({ api: { eventHub: { plan: vi.fn().mockResolvedValue(plan), enquiry: enquiryAct, matches: vi.fn().mockResolvedValue({ results: [] }) } } }));
const { EventPlanPage } = await import('./EventPlanPage');

describe('Event plan page', () => {
  it('shows the itemised quote from the server and sends a change request', async () => {
    renderWithProviders(<Routes><Route path="/events/plans/:id" element={<EventPlanPage />} /></Routes>, { route: '/events/plans/pl1' });
    expect(await screen.findByText('Parents’ 25th anniversary')).toBeInTheDocument();
    expect(screen.getByText('Kalpavruksha Celebrations')).toBeInTheDocument();
    expect(screen.getByText(/56,640/)).toBeInTheDocument();
    expect(screen.getByText('Optional')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Request changes' }));
    const sheet = screen.getByRole('dialog', { name: 'Request changes' });
    await userEvent.type(within(sheet).getByRole('textbox'), 'Add a cake');
    await userEvent.click(within(sheet).getByRole('button', { name: 'Send change request' }));
    await vi.waitFor(() => expect(enquiryAct).toHaveBeenCalledWith('e1', 'changes', 'Add a cake'));
    expect(await screen.findByText('Changes requested')).toBeInTheDocument();
  });
});
