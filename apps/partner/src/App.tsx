import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { ErrorState } from '@click/ui';
import type { OnboardingStep } from '@click/api';
import { PageLoader } from './components/OnboardingLayout';
import { useReducedMotion } from './components/useReducedMotion';
import { apiMessage } from './lib/format';
import { LoginPage } from './pages/LoginPage';
import { Splash } from './pages/Splash';
import { VerifyPage } from './pages/VerifyPage';
import { usePartnerSession } from './session/PartnerSession';
import { canVisit, STEP_ROUTE } from './session/steps';

// Onboarding and Home are loaded only when needed, keeping startup light.
const CategoryPage = lazy(() => import('./pages/onboarding/CategoryPage').then((m) => ({ default: m.CategoryPage })));
const ProfilePage = lazy(() => import('./pages/onboarding/ProfilePage').then((m) => ({ default: m.ProfilePage })));
const LocationPage = lazy(() => import('./pages/onboarding/LocationPage').then((m) => ({ default: m.LocationPage })));
const ReviewPage = lazy(() => import('./pages/onboarding/ReviewPage').then((m) => ({ default: m.ReviewPage })));
const CardPage = lazy(() => import('./pages/CardPage').then((m) => ({ default: m.CardPage })));
const HomePage = lazy(() => import('./pages/HomePage').then((m) => ({ default: m.HomePage })));

const SPLASH_MIN_MS = 1800;

/** UX routing only; the API enforces authentication and ownership on every request. */
function SignedIn({ children }: { children: (step: OnboardingStep) => ReactNode }) {
  const { status, partner } = usePartnerSession();
  if (status !== 'signed_in') return <Navigate to="/login" replace />;
  if (partner.error && !partner.state) {
    return <main id="main" className="center-page"><ErrorState error={new Error(apiMessage(partner.error))} onRetry={partner.refetch} /></main>;
  }
  if (!partner.state) return <PageLoader label="Loading your Partner profile" />;
  return <>{children(partner.state.onboardingStep)}</>;
}

function Step({ step, element }: { step: OnboardingStep; element: ReactNode }) {
  return (
    <SignedIn>
      {(current) => {
        // Finishing the review step is the moment the Partner ID is created: show the card first.
        if (current === 'complete') {
          return step === 'review' ? <Navigate to="/card" replace state={{ justCreated: true }} /> : <Navigate to="/home" replace />;
        }
        if (!canVisit(step, current)) return <Navigate to={STEP_ROUTE[current]} replace />;
        return element;
      }}
    </SignedIn>
  );
}

function Onboarded({ element }: { element: ReactNode }) {
  return <SignedIn>{(current) => (current === 'complete' ? element : <Navigate to={STEP_ROUTE[current]} replace />)}</SignedIn>;
}

function SignedOutOnly({ element }: { element: ReactNode }) {
  const { status } = usePartnerSession();
  return status === 'signed_in' ? <Navigate to="/" replace /> : <>{element}</>;
}

function Resolve() {
  const { status } = usePartnerSession();
  if (status !== 'signed_in') return <Navigate to="/login" replace />;
  return <SignedIn>{(current) => <Navigate to={STEP_ROUTE[current]} replace />}</SignedIn>;
}

export function App() {
  const { status, partner } = usePartnerSession();
  const reduced = useReducedMotion();
  const [minElapsed, setMinElapsed] = useState(false);
  const [splashGone, setSplashGone] = useState(false);

  useEffect(() => {
    const id = window.setTimeout(() => setMinElapsed(true), reduced ? 300 : SPLASH_MIN_MS);
    return () => window.clearTimeout(id);
  }, [reduced]);

  // Stay on the splash until we know where the partner belongs (session + partner record).
  const ready = minElapsed && status !== 'booting' && !(status === 'signed_in' && partner.isLoading);
  useEffect(() => {
    if (!ready || splashGone) return;
    const id = window.setTimeout(() => setSplashGone(true), reduced ? 0 : 450);
    return () => window.clearTimeout(id);
  }, [ready, splashGone, reduced]);

  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      {ready && (
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route index element={<Resolve />} />
            <Route path="login" element={<SignedOutOnly element={<LoginPage />} />} />
            <Route path="verify" element={<SignedOutOnly element={<VerifyPage />} />} />
            <Route path="onboarding/category" element={<Step step="category" element={<CategoryPage />} />} />
            <Route path="onboarding/profile" element={<Step step="profile" element={<ProfilePage />} />} />
            <Route path="onboarding/location" element={<Step step="location" element={<LocationPage />} />} />
            <Route path="onboarding/review" element={<Step step="review" element={<ReviewPage />} />} />
            <Route path="card" element={<Onboarded element={<CardPage />} />} />
            <Route path="home" element={<Onboarded element={<HomePage />} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      )}
      {!splashGone && <Splash leaving={ready} />}
    </>
  );
}
