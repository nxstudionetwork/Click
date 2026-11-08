import { useAuth } from '../auth/AuthProvider';
import { BuzzPreview } from '../features/home/BuzzPreview';
import { DiscoverySection } from '../features/home/DiscoverySection';
import { HomeHero } from '../features/home/HomeHero';
import { OfferCarousel } from '../features/home/OfferCarousel';
import { QuickServices } from '../features/home/QuickServices';
import { MomentSections, NearbySection, PopularSection } from '../features/home/StoreSections';
import { MoneyCards, RecentActivity } from '../features/home/YourClick';

/**
 * Click. Home: a composition of real data from existing domains (stores, offers, events, Buzz, orders,
 * bookings, rewards, wallet). Header, location and search live in the shell above it. Each section owns its
 * loading, empty and error state, so one failing service never blanks the page.
 */
export function HomePage() {
  const { status } = useAuth();
  const authed = status === 'authenticated';
  return (
    <div className="home">
      <HomeHero />
      <QuickServices />
      <OfferCarousel />
      <NearbySection />
      <PopularSection />
      <DiscoverySection />
      <BuzzPreview />
      {authed && <RecentActivity />}
      {authed && <MoneyCards />}
      <MomentSections />
    </div>
  );
}
