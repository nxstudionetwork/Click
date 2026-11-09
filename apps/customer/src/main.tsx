import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { App } from './App';
import { AuthProvider } from './auth/AuthProvider';
import { ConfirmProvider, ToastProvider } from './components/ui';
import { LocationProvider } from './location/LocationProvider';
import './styles/tokens.css';
import './styles/base.css';
import '@click/ui/ui.css';
import './styles/ui.css';
import './styles/layout.css';
import './styles/features.css';
import './styles/onboarding.css';
import './styles/home.css';
import './styles/explore.css';
import './styles/profile.css';
import './styles/service.css';
import './styles/ride.css';
import './styles/shop.css';
import './styles/showtime.css';
import './styles/groceries.css';
import './styles/parcel.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // Don't retry client errors (4xx); retry transient failures twice.
      retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
    },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <LocationProvider>
            <ToastProvider>
              <ConfirmProvider>
                <App />
              </ConfirmProvider>
            </ToastProvider>
          </LocationProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
