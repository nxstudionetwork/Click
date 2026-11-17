import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '@click/ui';
import type { KitchenBoard, Partner, PartnerHome, RestaurantOperations } from '@click/api';

const api = vi.hoisted(() => ({
  partner: { home: vi.fn(), act: vi.fn() },
  restaurant: { kitchen: vi.fn(), menu: vi.fn(), updateItem: vi.fn() },
}));
vi.mock('../lib/api', () => ({ api }));

const partner = {
  partnerCode: 'CLK-PT-000009', status: 'active', statusLabel: 'Active', isVerified: true, businessName: 'Basil & Lime', mode: 'restaurant',
  partnerType: { slug: 'food', name: 'Food & Dining', icon: 'food' },
  category: { slug: 'restaurant', name: 'Restaurant', icon: 'food', description: '', imageUrl: '', configuration: {} },
} as unknown as Partner;
vi.mock('../session/PartnerSession', () => ({
  PARTNER_QUERY_KEY: ['partner', 'me'],
  usePartnerSession: () => ({ partner: { state: { partner, onboardingStep: 'complete' } }, logout: vi.fn() }),
}));

import { navItems } from '../components/AppShell';
import { KitchenPage } from '../pages/restaurant/KitchenPage';
import { MenuPage } from '../pages/restaurant/MenuPage';

const ops: RestaurantOperations = { state: 'open', label: 'Open', prepTimeMinutes: 20, busyExtraMinutes: 0, busyUntil: null, pausedUntil: null, pauseReason: '',
  deliveryWindow: '30–45 min', busyChoices: [10, 20, 30], pauseChoices: [30], pauseReasons: [] };
const liveHome = { workspace: { kind: 'orders', state: 'live', workNoun: 'order' }, notifications: { unread: 0 } } as unknown as PartnerHome;

function renderPage(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}><ToastProvider><MemoryRouter>{ui}</MemoryRouter></ToastProvider></QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.partner.home.mockResolvedValue(liveHome);
});

test('restaurant navigation is Home | Orders | Kitchen | Menu | More on the phone, and only for restaurants', () => {
  expect(navItems(liveHome, 'restaurant').filter((i) => i.tab).map((i) => i.label)).toEqual(['Home', 'Orders', 'Kitchen', 'Menu', 'More']);
  expect(navItems(liveHome, 'store').map((i) => i.label)).toEqual(['Home', 'Orders', 'Earnings', 'Alerts']);
  const notConnected = { ...liveHome, workspace: { ...liveHome.workspace, state: 'not_connected' } } as PartnerHome;
  expect(navItems(notConnected, 'restaurant').map((i) => i.label)).toEqual(['Home', 'Alerts']);
});

test('kitchen tickets show items, notes and the next step, and the step goes to the server', async () => {
  const board: KitchenBoard = {
    prepTimeMinutes: 20, operations: ops,
    columns: [
      { key: 'new', label: 'New', items: [] },
      { key: 'accepted', label: 'Accepted', items: [] },
      { key: 'preparing', label: 'Preparing', items: [{
        kind: 'order', id: 'o1', ref: 'CLK-K3WQM62Q', title: 'Order CLK-K3WQM62Q', subtitle: '2 items', status: 'preparing',
        statusLabel: 'Preparing', tone: 'active', at: new Date().toISOString(), amount: '729.90', currency: 'INR', fields: [],
        actions: [{ key: 'ready', label: 'Mark ready', style: 'primary', confirm: '', needsReason: false }], navigate: null, link: '',
        kitchen: { lines: [{ quantity: 2, name: 'Green Curry', options: '', note: 'Less spicy please' }], note: '', orderType: 'Delivery',
          placedAt: new Date().toISOString(), readyBy: new Date(Date.now() - 60_000).toISOString(), late: true, readyAt: null, handover: '' },
      }] },
      { key: 'ready', label: 'Ready', items: [] },
    ],
  };
  api.restaurant.kitchen.mockResolvedValue(board);
  api.partner.act.mockResolvedValue({ ok: true, item: null });
  renderPage(<KitchenPage />);

  const col = await screen.findByRole('region', { name: /preparing/i });
  expect(within(col).getByText('Green Curry')).toBeInTheDocument();
  expect(within(col).getByText('“Less spicy please”')).toBeInTheDocument();
  expect(within(col).getByText(/Late — target was/)).toBeInTheDocument();
  await userEvent.click(within(col).getByRole('button', { name: 'Mark ready' }));
  await waitFor(() => expect(api.partner.act).toHaveBeenCalledWith(expect.objectContaining({ id: 'o1' }), 'ready', undefined));
});

test('marking a menu item unavailable is one tap and is saved on the server', async () => {
  const item = { id: 'i1', categoryId: 'c1', name: 'Pad Thai', description: '', imageUrl: '', price: '349.00', dietary: 'non_veg',
    isAvailable: true, isActive: true, isFeatured: false, position: 1, unitsSold: 0, ratingAverage: 0, ratingCount: 0, optionGroups: [] };
  api.restaurant.menu.mockResolvedValue({
    store: { id: 's1', name: 'Basil & Lime', operations: ops, stores: [] }, uncategorised: [], dietary: [],
    counts: { items: 1, available: 1, unavailable: 0, hidden: 0 },
    categories: [{ id: 'c1', name: 'Thai', position: 1, isActive: true, items: [item] }],
  });
  api.restaurant.updateItem.mockResolvedValue({ ...item, isAvailable: false });
  renderPage(<MenuPage />);

  const toggle = await screen.findByRole('switch', { name: 'Pad Thai available to order' });
  await userEvent.click(toggle);
  await waitFor(() => expect(api.restaurant.updateItem).toHaveBeenCalledWith('i1', { isAvailable: false }));
});
