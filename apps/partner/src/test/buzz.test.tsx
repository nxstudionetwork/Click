import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '@click/ui';
import type { Partner, PartnerBuzzOverview, PartnerBuzzPost } from '@click/api';

const api = vi.hoisted(() => ({
  partner: { home: vi.fn() },
  buzz: { overview: vi.fn(), create: vi.fn(), update: vi.fn(), act: vi.fn(), remove: vi.fn(), upload: vi.fn(), community: vi.fn() },
  buzzEngage: { like: vi.fn(), report: vi.fn() },
}));
vi.mock('../lib/api', () => ({ api }));
const partner = { partnerCode: 'CLK-PT-000009', status: 'active', statusLabel: 'Active', isVerified: true, businessName: 'Basil & Lime', mode: 'restaurant',
  partnerType: { slug: 'food', name: 'Food', icon: 'food' }, category: { slug: 'restaurant', name: 'Restaurant', icon: 'food' } } as unknown as Partner;
vi.mock('../session/PartnerSession', () => ({
  PARTNER_QUERY_KEY: ['partner', 'me'],
  usePartnerSession: () => ({ partner: { state: { partner, onboardingStep: 'complete' } }, logout: vi.fn() }),
}));

import { BuzzPage } from '../pages/BuzzPage';

const live: PartnerBuzzPost = {
  id: 'p1', kind: 'new_item', kindLabel: 'Something new', headline: 'Chicken Biryani — ₹199 today', caption: 'Only today', audience: 'public',
  targetType: 'store', targetId: 's1', targetTitle: 'Basil & Lime', cta: 'order', ctaLabel: 'Order now', link: '/stores/basil',
  product: { id: 'i1', name: 'Chicken Biryani', price: '199.00', available: false }, offer: null, media: [], status: 'live', statusLabel: 'Live',
  reviewNote: '', publishAt: null, expiresAt: new Date(Date.now() + 86_400_000).toISOString(), submittedAt: null, createdAt: new Date().toISOString(),
  stats: { views: 120, ctaClicks: 18, likes: 9, saves: 3, ctr: 15, openReports: 0 }, actions: ['edit', 'pause', 'archive', 'delete'],
};
const overview: PartnerBuzzOverview = {
  posts: [live], counts: [{ status: 'live', count: 1 }], totals: { views7d: 120, clicks7d: 18, likes: 9, saves: 3 }, canPublish: true,
  listings: [{ type: 'store', id: 's1', title: 'Basil & Lime', link: '/stores/basil', ctas: ['order', 'view_menu'], handle: 'basil' }],
  ctaLabels: [{ value: 'order', label: 'Order now' }, { value: 'view_menu', label: 'View menu' }], kinds: [{ value: 'update', label: 'Business update' }, { value: 'new_item', label: 'Something new' }],
  products: [{ id: 'i1', storeId: 's1', name: 'Chicken Biryani', price: '199.00', available: false }], offers: [],
  limits: { media: 4, videoMb: 25, imageMb: 8, maxDays: 90 },
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><ToastProvider><MemoryRouter><BuzzPage /></MemoryRouter></ToastProvider></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  api.partner.home.mockResolvedValue({ workspace: { kind: 'orders', state: 'live', workNoun: 'order' }, notifications: { unread: 0 } });
  api.buzz.overview.mockResolvedValue(overview);
});

test('a live post shows its real performance, the attached item’s availability and its actions', async () => {
  api.buzz.act.mockResolvedValue({ ...live, status: 'paused' });
  renderPage();
  const card = (await screen.findByRole('heading', { name: 'Chicken Biryani — ₹199 today' })).closest('li')!;
  expect(within(card).getByText('15%')).toBeInTheDocument();
  expect(within(card).getByText('(unavailable now)')).toBeInTheDocument();
  await userEvent.click(within(card).getByRole('button', { name: 'Pause' }));
  await waitFor(() => expect(api.buzz.act).toHaveBeenCalledWith('p1', 'pause'));
});

test('the composer previews the post and sends it to Click for review with the chosen button and item', async () => {
  api.buzz.create.mockResolvedValue({ ...live, status: 'in_review' });
  renderPage();
  await userEvent.click(await screen.findByRole('button', { name: /Create post/ }));
  await userEvent.type(screen.getByLabelText('Headline'), 'Weekend biryani');
  expect(within(screen.getByRole('complementary', { name: 'Preview' })).getByText('Weekend biryani')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'View menu' }));
  await userEvent.selectOptions(screen.getByLabelText(/Feature an item/), 'i1');
  expect(screen.getByText(/Customers will see it as unavailable/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Send for review' }));
  await waitFor(() => expect(api.buzz.create).toHaveBeenCalled());
  const body = api.buzz.create.mock.calls[0]![0];
  expect(body).toMatchObject({ headline: 'Weekend biryani', targetType: 'store', targetId: 's1', cta: 'view_menu', productId: 'i1', submit: true, publishAt: null });
  expect(new Date(body.expiresAt).getTime() - Date.now()).toBeGreaterThan(6.9 * 86_400_000);  // default: 7 days
});
