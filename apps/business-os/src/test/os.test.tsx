import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '@click/ui';
import type { OSContext } from '@click/api';
import { RequirePerm } from '../App';
import { Shell } from '../components/Shell';
import { SessionContext, type SessionValue } from '../session/OSSession';
import { LoginPage } from '../pages/LoginPage';

function ctx(over: Partial<OSContext> = {}): OSContext {
  return {
    user: { id: 'u1', fullName: 'Divya Patel', email: 'divya@click.dev', phone: '', avatarUrl: null },
    account: { id: 'a1', kind: 'employee', status: 'active', mfaEnabled: false, onboardingRequired: false, timezone: 'Asia/Kolkata', language: 'en',
      lastLoginAt: null, accessVersion: 1, preferences: {}, partner: null },
    employee: null,
    organization: { id: 'o1', name: 'Click', code: 'click', currency: 'INR', timezone: 'Asia/Kolkata' },
    orgContext: { units: [], location: null, department: null, team: null },
    contextOptions: { orgWide: false, units: [], selected: null, switchable: false },
    isManager: false,
    directReports: 0,
    roles: [{ id: 'r1', key: 'employee', name: 'Employee' }],
    permissions: [{ code: 'finance.expense.create', scope: 'own' }],
    mfaBlocked: [],
    approvalAuthority: [],
    navigation: [
      { key: 'core', label: 'Core', items: [{ key: 'home', label: 'Home', icon: 'home', path: '/home', status: 'live' }] },
      { key: 'business', label: 'Business', items: [{ key: 'finance', label: 'Finance', icon: 'receipt', path: '/m/finance', status: 'foundation' }] },
    ],
    quickActions: [],
    session: null,
    security: { sensitiveRequiresMfa: false, idleMinutes: 60 },
    ...over,
  };
}

function wrap(ui: React.ReactNode, context: OSContext | undefined = ctx(), path = '/') {
  const value: SessionValue = {
    status: context ? 'signed_in' : 'signed_out', bootError: null, retryBoot: () => {}, context, contextError: null,
    refetchContext: () => {}, setContext: () => {}, completeSignIn: async () => {}, logout: async () => {},
  };
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <SessionContext.Provider value={value}><ToastProvider>{ui}</ToastProvider></SessionContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    const body = url.includes('/os/notifications/summary') ? { unread: 2, critical: 0 }
      : url.includes('/os/approvals') ? { results: [], box: 'inbox', counts: { inbox: 0, minePending: 0 } }
      : url.includes('/os/auth/identify') ? { flowToken: 'f', accessType: 'employee', methods: ['password'], sso: null }
      : url.includes('/os/auth/dev-personas') ? { results: [] } : {};
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
});
afterEach(() => vi.restoreAllMocks());

test('sidebar renders only the navigation the server granted', async () => {
  wrap(<Shell><p>content</p></Shell>);
  expect(screen.getByRole('link', { name: /Finance/ })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /Users/ })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /Roles & Permissions/ })).not.toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole('button', { name: /Notifications, 2 unread/ })).toBeInTheDocument());
});

test('RequirePerm shows a permission-denied state instead of the page', () => {
  wrap(<RequirePerm any={['identity.user.view']}><p>secret admin page</p></RequirePerm>);
  expect(screen.queryByText('secret admin page')).not.toBeInTheDocument();
  expect(screen.getByText(/don’t have access/)).toBeInTheDocument();
});

test('RequirePerm explains when two-step verification unlocks the page', () => {
  wrap(<RequirePerm any={['identity.user.view']}><p>admin</p></RequirePerm>, ctx({ mfaBlocked: ['identity.user.view'] }));
  expect(screen.getByText('Two-step verification required')).toBeInTheDocument();
});

test('login asks how you are accessing, then the identifier, then the password', async () => {
  const user = userEvent.setup();
  wrap(<Routes><Route path="/login" element={<LoginPage />} /></Routes>, undefined, '/login');
  expect(screen.getByText('How are you accessing Click Business OS?')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: /Administrator/ }));
  expect(screen.getByText(/Signing in as/)).toHaveTextContent('Administrator');
  await user.type(screen.getByLabelText(/Work email or employee ID/), 'CLK-E-0002');
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  expect(await screen.findByLabelText('Password')).toBeInTheDocument();
});

test('People & HR navigation shows only the sections the server returns', async () => {
  const { PeopleLayout } = await import('../pages/people/common');
  vi.mocked(globalThis.fetch).mockImplementation(async (input) => {
    const url = String(input);
    const body = url.includes('/os/people/nav')
      ? { sections: [{ key: 'experience', label: 'Employee experience', items: [{ key: 'me', label: 'My HR', path: '/people/me' }] }], hasEmployeeRecord: true, isManager: false }
      : {};
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  wrap(<Routes><Route path="/people" element={<PeopleLayout />} /></Routes>, ctx(), '/people');
  expect(await screen.findByRole('link', { name: 'My HR' })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /Compensation/ })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /Employee relations/ })).not.toBeInTheDocument();
});
