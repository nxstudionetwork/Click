import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError } from '@click/api';
import { ToastProvider } from '@click/ui';
import { App } from './App';
import { PartnerSessionProvider } from './session/PartnerSession';
import './styles/tokens.css';
import './styles/base.css';
import '@click/ui/ui.css';
import './styles/partner.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
    },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <PartnerSessionProvider>
          <ToastProvider>
            <App />
          </ToastProvider>
        </PartnerSessionProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
