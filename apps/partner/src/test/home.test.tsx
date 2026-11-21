import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '@click/ui';
import type { Partner, PartnerHome, WorkItem } from '@click/api';
import { ApiError } from '@click/api';

const api = vi.hoisted(() => ({ partner: { home: vi.fn(), setAvailability: vi.fn(), act: vi.fn(), reportDriverLocation: vi.fn() } }));
vi.mock('../lib/api', () => ({ api }));

const partner = {
  partnerCode: 'CLK-PT-000245', status: 'active', statusLabel: 'Active', isVerified: true, businessName: 'Fresh Bowl',
  partnerType: { slug: 'food', name: 'Food & Dining', icon: 'food' },
  category: { slug: 'restaurant', name: 'Restaurant', icon: 'food', description: '', imageUrl: '', configuration: {} },
  profile: { contactName: 'Asha Rao', email: '', description: '', details: {} }, onboardingStep: 'complete',
} as unknown as Partner;
vi.mock('../session/PartnerSession', () => ({
  PARTNER_QUERY_KEY: ['partner', 'me'],
  usePartnerSession: () => ({ partner: { state: { partner, onboardingStep: 'complete' } }, logout: vi.fn() }),
}));

import { HomePage } from '../pages/HomePage';

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) { this.open = true; };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) { this.open = false; };
});

const order: WorkItem = {
  kind: 'order', id: 'o1', ref: 'CLK-ABCD1234', title: 'Order CLK-ABCD1234', subtitle: '2 items', status: 'placed',
  statusLabel: 'New order', tone: 'urgent', at: new Date().toISOString(), amount: '420.00', currency: 'INR',
  fields: [{ label: 'Items', value: '2 × Paneer Bowl' }],
  actions: [{ key: 'accept', label: 'Accept order', style: 'primary', confirm: '', needsReason: false },
    { key: 'reject', label: 'Reject', style: 'danger', confirm: 'The customer will be told.', needsReason: true }],
  navigate: null, link: '',
};

function home(over: Partial<PartnerHome> = {}): PartnerHome {
  return {
    generatedAt: new Date().toISOString(),
    workspace: { kind: 'orders', state: 'live', message: '', workNoun: 'order', location: 'business', liveLocation: null },
    greetingName: 'Fresh Bowl', context: 'You have 1 new order waiting for you to accept.',
    availability: { isOn: true, label: 'Open', onLabel: 'Open', offLabel: 'Closed', turnOn: 'Open restaurant', turnOff: 'Close restaurant',
      hint: 'Customers can order from you now.', canChange: true, blockedReason: '', confirmOff: 'Customers won’t be able to order.', since: null },
    actionRequired: { status: 'ok', data: [order] },
    active: { status: 'ok', data: [] },
    incoming: { status: 'ok', data: [] },
    metrics: { status: 'ok', data: [{ key: 'orders', label: 'Orders', value: 1, display: '1', hint: 'Placed today' }] },
    earnings: { status: 'ok', data: { label: 'Today’s sales', today: '420.00', todayCount: 1, week: '420.00', weekCount: 1, currency: 'INR', note: '', countLabel: 'orders' } },
    performance: { status: 'error', message: 'This section couldn’t load. Try again in a moment.' },
    activity: { status: 'ok', data: [] },
    quickActions: [{ key: 'new', label: 'New orders', icon: 'bell', to: '/work?view=new', count: 1 }],
    notifications: { unread: 3 },
    ...over,
  };
}

function renderHome() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}><ToastProvider><MemoryRouter><HomePage /></MemoryRouter></ToastProvider></QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe('Partner Home', () => {
  it('shows identity, category status, real work and lets one section fail on its own', async () => {
    api.partner.home.mockResolvedValue(home());
    renderHome();
    expect(await screen.findByRole('heading', { name: /Fresh Bowl$/ })).toBeInTheDocument();
    expect(screen.getAllByText('CLK-PT-000245').length).toBeGreaterThan(0);
    expect(screen.getByText('Open')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Order CLK-ABCD1234' })).toBeInTheDocument();
    expect(screen.getByText('1 order today')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('This section couldn’t load');
    expect(screen.getByRole('link', { name: 'Notifications, 3 unread' })).toBeInTheDocument();
  });

  it('asks before closing and only shows the new state after the server confirms it', async () => {
    api.partner.home.mockResolvedValue(home());
    api.partner.setAvailability.mockRejectedValue(new ApiError(409, { code: 'availability_not_allowed', message: 'Finish your current trip first.' }));
    renderHome();
    await userEvent.click(await screen.findByRole('button', { name: 'Close restaurant' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Close restaurant' }));
    expect(api.partner.setAvailability).toHaveBeenCalledWith(false);
    expect(await within(dialog).findByText('Finish your current trip first.')).toBeInTheDocument();
    expect(screen.getByText('Open')).toBeInTheDocument();
  });

  it('requires a reason to reject and sends it to the server', async () => {
    api.partner.home.mockResolvedValue(home());
    api.partner.act.mockResolvedValue({ ok: true, item: null });
    renderHome();
    await userEvent.click(await screen.findByRole('button', { name: 'Reject' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Reject' }));
    expect(api.partner.act).not.toHaveBeenCalled();
    await userEvent.type(within(dialog).getByRole('textbox'), 'Out of paneer');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Reject' }));
    await waitFor(() => expect(api.partner.act).toHaveBeenCalledWith({ ...order }, 'reject', { reason: 'Out of paneer' }));
  });

  it('is honest when the service has not launched: no metrics, no toggle, no dead links', async () => {
    const off = { status: 'unavailable' as const, message: 'Click. Stays isn’t open to customers yet.' };
    api.partner.home.mockResolvedValue(home({
      workspace: { kind: 'upcoming', state: 'upcoming', message: 'Click. Stays isn’t open to customers yet.', workNoun: 'booking', location: 'business', liveLocation: null },
      availability: { ...home().availability, isOn: false, canChange: false, blockedReason: 'You can switch to “Accepting bookings” once Click. Stays launches.' },
      actionRequired: off, active: off, incoming: off, metrics: off, earnings: off, performance: off, activity: off, quickActions: [],
    }));
    renderHome();
    expect(await screen.findByRole('heading', { name: 'Coming to Click' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /restaurant/ })).not.toBeInTheDocument();
    expect(screen.queryByText('Today’s overview')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Earnings/ })).not.toBeInTheDocument();
  });

  it('shows a retryable error when the dashboard cannot load', async () => {
    api.partner.home.mockRejectedValue(new ApiError(0, { code: 'network_error', message: 'offline' }));
    renderHome();
    expect(await screen.findByText('Couldn’t load your dashboard')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});
