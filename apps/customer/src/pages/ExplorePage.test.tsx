import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '../test/utils';
import { CLICK_FEATURES } from '../config/services';
import { EXPLORE_BANNERS } from '../config/explore';

vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ status: 'authenticated', user: { fullName: 'Asha Rao' } }) }));
vi.mock('../lib/api', () => ({ api: {
  catalog: { offers: vi.fn().mockResolvedValue({ count: 20, results: [] }) },
  customer: {
    wallet: vi.fn().mockResolvedValue({ balance: '3806.15', currency: 'INR', transactions: [], topUpAvailable: false }),
    rewards: vi.fn().mockResolvedValue({ balance: 827, earned: 827, used: 0, history: [], rules: {} }),
  },
} }));
const { ExplorePage } = await import('./ExplorePage');

describe('Explore', () => {
  beforeEach(() => localStorage.clear());

  it('lists every Click. feature from the central registry, alphabetically, each linking to its real route', () => {
    renderWithProviders(<ExplorePage />);
    const grid = screen.getByRole('heading', { name: 'Click. Features' }).parentElement!;
    const links = within(grid).getAllByRole('link');
    const names = links.map((l) => l.querySelector('.xfeature__name')!.textContent!);
    expect(names).toEqual([...names].sort((a, b) => a.localeCompare(b, 'en', { sensitivity: 'base' })));
    expect(names).toEqual(CLICK_FEATURES.map((f) => f.name));
    for (const n of ['Activity', 'Buddy', 'Buzz', 'Food', 'Groceries', 'Movies', 'Offers', 'Rewards', 'Shopping', 'Wallet']) expect(names).toContain(n);
    const href = (n: string) => links[names.indexOf(n)]!.getAttribute('href');
    expect(href('Food')).toBe('/food');
    expect(href('Buzz')).toBe('/buzz');
    expect(href('Wallet')).toBe('/wallet');
    expect(href('Events')).toBe('/movies?tab=events');
    // Only services that genuinely haven't launched say so.
    expect(within(links[names.indexOf('Rides')]!).getByText('Soon')).toBeInTheDocument();
    expect(links[names.indexOf('Rides')]).toHaveAccessibleName(/coming soon/);
    expect(within(links[names.indexOf('Food')]!).queryByText('Soon')).toBeNull();
  });

  it('Your Click. shows real figures: wallet masked until revealed, real points and offers', async () => {
    renderWithProviders(<ExplorePage />);
    expect(await screen.findByText('827 pts')).toBeInTheDocument();
    expect(await screen.findByText('20 live')).toBeInTheDocument();
    expect(await screen.findByText('₹ ••••')).toBeInTheDocument();
    expect(screen.queryByText(/3,806/)).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Show wallet balance' }));
    expect(screen.getByText(/3,806\.15/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open your activity/ })).toHaveAttribute('href', '/activity');
  });

  it('Account rows open the existing pages; the footer carries the tagline and IFX attribution', () => {
    renderWithProviders(<ExplorePage />);
    const account = screen.getByRole('navigation', { name: 'Account' });
    expect(within(account).getAllByRole('link').map((l) => [l.querySelector('strong')!.textContent, l.getAttribute('href')])).toEqual([
      ['Payments', '/account/payments'], ['Settings', '/settings'], ['Help & Support', '/help'], ['Addresses', '/account/addresses'],
    ]);
    expect(screen.getByText('A venture of IFX Group')).toBeInTheDocument();
    expect(document.body.textContent).toContain('Everything you need.One Click. away.');
    expect(document.body.textContent).not.toMatch(/\bMenu\b/);
  });

  it('shows the next banner each time Explore opens (deterministic rotation)', () => {
    const seen: string[] = [];
    for (let i = 0; i < EXPLORE_BANNERS.length + 1; i++) {
      const { unmount } = renderWithProviders(<ExplorePage />);
      seen.push(document.querySelector('.xbanner__title')!.textContent!);
      unmount();
    }
    const expected = EXPLORE_BANNERS.map((b) => b.title + (b.titleAccent ?? ''));
    expect(seen).toEqual([...expected, expected[0]]);
  });

  it('banner actions point at real routes', () => {
    for (const b of EXPLORE_BANNERS) if (b.action) expect(b.action.to).toMatch(/^\/(food|shopping|buzz|movies|offers|rides|groceries)/);
  });
});
