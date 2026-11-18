import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthProvider';
import { api } from '../lib/api';
import { BuzzPreview } from '../features/home/BuzzPreview';
import { DiscoverySection } from '../features/home/DiscoverySection';
import { HomeHero } from '../features/home/HomeHero';
import { OfferCarousel } from '../features/home/OfferCarousel';
import { QuickServices } from '../features/home/QuickServices';
import { ShoppingPicks } from '../features/home/ShoppingPicks';
import { MomentSections, NearbySection, PopularSection } from '../features/home/StoreSections';
import { MoneyCards, RecentActivity } from '../features/home/YourClick';

/**
 * Click. Home: a composition of real data from existing domains (stores, offers, events, Shopping, Buzz, orders,
 * bookings, rewards, wallet). Header, location and search live in the shell above it. Each section owns its
 * loading, empty and error state, so one failing service never blanks the page.
 */
export function HomePage() {
  const { status } = useAuth();
  const authed = status === 'authenticated';
  // Click. operations can turn sections off or reorder them (/home/layout); without a layout the default order is used.
  const layout = useQuery({ queryKey: ['home', 'layout'], queryFn: api.money.homeLayout, staleTime: 10 * 60_000 });
  const SECTIONS: Record<string, ReactNode> = {
    hero: <HomeHero />, quick: <QuickServices />, offers: <OfferCarousel />, nearby: <NearbySection />, popular: <PopularSection />,
    discovery: <DiscoverySection />, shopping: <ShoppingPicks />, buzz: <BuzzPreview />, recent: authed ? <RecentActivity /> : null,
    money: authed ? <MoneyCards /> : null, moments: <MomentSections />,
  };
  const order = layout.data?.sections ?? Object.keys(SECTIONS);
  return <div className="home">{order.filter((c) => c in SECTIONS).map((c) => <div key={c} className="home__slot">{SECTIONS[c]}</div>)}</div>;
}
