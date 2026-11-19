import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { ErrorState } from '@click/ui';
import { Shell } from './components/Shell';
import { Empty, Forbidden, MfaNeeded, PageLoader } from './components/ui';
import { useAccess } from './session/access';
import { useOSSession } from './session/OSSession';
import { Splash } from './pages/Splash';
import { LoginPage } from './pages/LoginPage';

const lazyPage = <K extends string>(loader: () => Promise<Record<K, React.ComponentType>>, name: K) =>
  lazy(() => loader().then((m) => ({ default: m[name] })));

const InvitePage = lazyPage(() => import('./pages/InvitePage'), 'InvitePage');
const OnboardingPage = lazyPage(() => import('./pages/OnboardingPage'), 'OnboardingPage');
const SessionEndedPage = lazyPage(() => import('./pages/SessionEndedPage'), 'SessionEndedPage');
const HomePage = lazyPage(() => import('./pages/HomePage'), 'HomePage');
const MyWorkPage = lazyPage(() => import('./pages/MyWorkPage'), 'MyWorkPage');
const ApprovalsPage = lazyPage(() => import('./pages/ApprovalsPage'), 'ApprovalsPage');
const ApprovalDetailPage = lazyPage(() => import('./pages/ApprovalDetailPage'), 'ApprovalDetailPage');
const NewApprovalPage = lazyPage(() => import('./pages/NewApprovalPage'), 'NewApprovalPage');
const TasksPage = lazyPage(() => import('./pages/TasksPage'), 'TasksPage');
const NotificationsPage = lazyPage(() => import('./pages/NotificationsPage'), 'NotificationsPage');
const CalendarPage = lazyPage(() => import('./pages/CalendarPage'), 'CalendarPage');
const SearchPage = lazyPage(() => import('./pages/SearchPage'), 'SearchPage');
const ProfilePage = lazyPage(() => import('./pages/ProfilePage'), 'ProfilePage');
const AlertsPage = lazyPage(() => import('./pages/AlertsPage'), 'AlertsPage');
const AnnouncementsPage = lazyPage(() => import('./pages/AnnouncementsPage'), 'AnnouncementsPage');
const PeopleLayout = lazyPage(() => import('./pages/people/common'), 'PeopleLayout');
const pCore = () => import('./pages/people/core');
const pTalent = () => import('./pages/people/talent');
const pWork = () => import('./pages/people/workforce');
const pGrowth = () => import('./pages/people/growth');
const pCare = () => import('./pages/people/care');
const pAccess = () => import('./pages/access');
const AccessLayout = lazyPage(pAccess, 'AccessLayout');
const AccessHome = lazyPage(pAccess, 'AccessHome');
const MyAccess = lazyPage(pAccess, 'MyAccess');
const EffectiveAccess = lazyPage(pAccess, 'EffectiveAccess');
const AccessSimulator = lazyPage(pAccess, 'Simulator');
const AccessWhoHas = lazyPage(pAccess, 'WhoHas');
const AccessCompare = lazyPage(pAccess, 'Compare');
const AccessPackages = lazyPage(pAccess, 'Packages');
const AccessRequests = lazyPage(pAccess, 'Requests');
const AccessReviews = lazyPage(pAccess, 'Reviews');
const AccessSoD = lazyPage(pAccess, 'SoD');
const AccessEmergency = lazyPage(pAccess, 'Emergency');
const AccessPrivileged = lazyPage(pAccess, 'Privileged');
const AccessHygiene = lazyPage(pAccess, 'Hygiene');
const AccessSecurity = lazyPage(pAccess, 'SecurityEvents');
const HRHome = lazyPage(pCore, 'HRHome');
const Directory = lazyPage(pCore, 'Directory');
const Profile360 = lazyPage(pCore, 'Profile');
const OrgChart = lazyPage(pCore, 'OrgChart');
const MyHR = lazyPage(pCore, 'MyHR');
const Positions = lazyPage(pTalent, 'Positions');
const Recruitment = lazyPage(pTalent, 'Recruitment');
const Candidates = lazyPage(pTalent, 'Candidates');
const Interviews = lazyPage(pTalent, 'Interviews');
const PeopleOnboarding = lazyPage(pTalent, 'Onboarding');
const Attendance = lazyPage(pWork, 'Attendance');
const Leave = lazyPage(pWork, 'Leave');
const Performance = lazyPage(pGrowth, 'Performance');
const Learning = lazyPage(pGrowth, 'Learning');
const Compensation = lazyPage(pGrowth, 'Compensation');
const Engagement = lazyPage(pGrowth, 'Engagement');
const HRRequests = lazyPage(pCare, 'Requests');
const HRCases = lazyPage(pCare, 'Cases');
const Lifecycle = lazyPage(pCare, 'Lifecycle');
const HRAnalytics = lazyPage(pCare, 'Analytics');
const HRSettings = lazyPage(pCare, 'HRSettings');
const ModulePage = lazyPage(() => import('./pages/ModulePage'), 'ModulePage');
const HelpPage = lazyPage(() => import('./pages/HelpPage'), 'HelpPage');
const SettingsLayout = lazyPage(() => import('./pages/settings/SettingsLayout'), 'SettingsLayout');
const PreferencesPage = lazyPage(() => import('./pages/settings/PreferencesPage'), 'PreferencesPage');
const SecurityPage = lazyPage(() => import('./pages/settings/SecurityPage'), 'SecurityPage');
const OrganizationPage = lazyPage(() => import('./pages/settings/OrganizationPage'), 'OrganizationPage');
const UsersPage = lazyPage(() => import('./pages/settings/UsersPage'), 'UsersPage');
const UserDetailPage = lazyPage(() => import('./pages/settings/UserDetailPage'), 'UserDetailPage');
const RolesPage = lazyPage(() => import('./pages/settings/RolesPage'), 'RolesPage');
const RoleDetailPage = lazyPage(() => import('./pages/settings/RoleDetailPage'), 'RoleDetailPage');
const WorkflowsPage = lazyPage(() => import('./pages/settings/WorkflowsPage'), 'WorkflowsPage');
const AuditPage = lazyPage(() => import('./pages/settings/AuditPage'), 'AuditPage');
const SystemPage = lazyPage(() => import('./pages/settings/SystemPage'), 'SystemPage');
const IntegrationsPage = lazyPage(() => import('./pages/settings/IntegrationsPage'), 'IntegrationsPage');

const SPLASH_MIN_MS = 1200;

function useTheme() {
  const { context } = useOSSession();
  const theme = context?.account.preferences.appearance?.theme ?? 'system';
  useEffect(() => {
    const apply = () => {
      const dark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
      document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    };
    apply();
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, [theme]);
}

/** UX routing only. The API authenticates and authorizes every request on its own. */
function SignedIn({ children }: { children: ReactNode }) {
  const { status, context, contextError, refetchContext } = useOSSession();
  const location = useLocation();
  if (status === 'expired') return <Navigate to="/session-ended" replace />;
  if (status !== 'signed_in') return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  if (!context) {
    return contextError
      ? <main className="center-page"><ErrorState error={contextError} onRetry={refetchContext} /></main>
      : <PageLoader label="Loading your workspace" />;
  }
  if (context.account.onboardingRequired && location.pathname !== '/onboarding') return <Navigate to="/onboarding" replace />;
  return <>{children}</>;
}

function InShell({ children }: { children: ReactNode }) {
  return (
    <SignedIn>
      <Shell><Suspense fallback={<PageLoader />}>{children}</Suspense></Shell>
    </SignedIn>
  );
}

/** Hides a page unless the person holds at least one of the permissions (the API refuses regardless). */
export function RequirePerm({ any, children }: { any: string[]; children: ReactNode }) {
  const access = useAccess();
  if (any.some(access.can)) return <>{children}</>;
  if (any.some(access.mfaBlocked)) return <MfaNeeded />;
  return <Forbidden />;
}

export function App() {
  const { status, bootError, retryBoot } = useOSSession();
  const [minElapsed, setMinElapsed] = useState(false);
  useTheme();
  useEffect(() => { const t = setTimeout(() => setMinElapsed(true), SPLASH_MIN_MS); return () => clearTimeout(t); }, []);

  if (status === 'booting' || !minElapsed) return <Splash status={status === 'booting' ? 'Securing your session' : 'Loading Business OS'} />;
  if (bootError && status === 'signed_out') {
    return <main className="center-page"><ErrorState error={new Error(bootError)} onRetry={retryBoot} /></main>;
  }

  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route path="/" element={<Navigate to={status === 'signed_in' ? '/home' : '/login'} replace />} />
        <Route path="/login" element={status === 'signed_in' ? <Navigate to="/home" replace /> : <LoginPage />} />
        <Route path="/invite/:token" element={<InvitePage />} />
        <Route path="/session-ended" element={<SessionEndedPage />} />
        <Route path="/onboarding" element={<SignedIn><OnboardingPage /></SignedIn>} />

        <Route path="/home" element={<InShell><HomePage /></InShell>} />
        <Route path="/my-work" element={<InShell><MyWorkPage /></InShell>} />
        <Route path="/approvals" element={<InShell><ApprovalsPage /></InShell>} />
        <Route path="/approvals/new" element={<InShell><NewApprovalPage /></InShell>} />
        <Route path="/approvals/:id" element={<InShell><ApprovalDetailPage /></InShell>} />
        <Route path="/tasks" element={<InShell><TasksPage /></InShell>} />
        <Route path="/notifications" element={<InShell><NotificationsPage /></InShell>} />
        <Route path="/calendar" element={<InShell><CalendarPage /></InShell>} />
        <Route path="/search" element={<InShell><SearchPage /></InShell>} />
        <Route path="/profile" element={<InShell><ProfilePage /></InShell>} />
        <Route path="/alerts" element={<InShell><AlertsPage /></InShell>} />
        <Route path="/announcements" element={<InShell><AnnouncementsPage /></InShell>} />
        <Route path="/access" element={<InShell><AccessLayout /></InShell>}>
          <Route index element={<AccessHome />} />
          <Route path="me" element={<MyAccess />} />
          <Route path="requests" element={<AccessRequests />} />
          <Route path="reviews" element={<AccessReviews />} />
          <Route path="emergency" element={<AccessEmergency />} />
          <Route path="effective" element={<RequirePerm any={['access.analysis.view']}><EffectiveAccess /></RequirePerm>} />
          <Route path="simulator" element={<RequirePerm any={['access.analysis.view']}><AccessSimulator /></RequirePerm>} />
          <Route path="who" element={<RequirePerm any={['access.analysis.view']}><AccessWhoHas /></RequirePerm>} />
          <Route path="compare" element={<RequirePerm any={['access.analysis.view']}><AccessCompare /></RequirePerm>} />
          <Route path="packages" element={<RequirePerm any={['access.package.view']}><AccessPackages /></RequirePerm>} />
          <Route path="sod" element={<RequirePerm any={['access.sod.view']}><AccessSoD /></RequirePerm>} />
          <Route path="privileged" element={<RequirePerm any={['access.analysis.view']}><AccessPrivileged /></RequirePerm>} />
          <Route path="hygiene" element={<RequirePerm any={['access.analysis.view']}><AccessHygiene /></RequirePerm>} />
          <Route path="security" element={<RequirePerm any={['identity.security.view']}><AccessSecurity /></RequirePerm>} />
        </Route>
        <Route path="/people" element={<InShell><PeopleLayout /></InShell>}>
          <Route index element={<HRHome />} />
          <Route path="me" element={<MyHR />} />
          <Route path="directory" element={<RequirePerm any={['people.directory.view']}><Directory /></RequirePerm>} />
          <Route path="org-chart" element={<RequirePerm any={['people.directory.view']}><OrgChart /></RequirePerm>} />
          <Route path="positions" element={<RequirePerm any={['people.position.view']}><Positions /></RequirePerm>} />
          <Route path="recruitment" element={<RequirePerm any={['people.recruitment.view']}><Recruitment /></RequirePerm>} />
          <Route path="candidates" element={<RequirePerm any={['people.candidate.view']}><Candidates /></RequirePerm>} />
          <Route path="interviews" element={<Interviews />} />
          <Route path="onboarding" element={<RequirePerm any={['people.onboarding.view']}><PeopleOnboarding /></RequirePerm>} />
          <Route path="attendance" element={<Attendance />} />
          <Route path="leave" element={<Leave />} />
          <Route path="performance" element={<Performance />} />
          <Route path="learning" element={<Learning />} />
          <Route path="compensation" element={<RequirePerm any={['people.payroll.view', 'people.benefit.view']}><Compensation /></RequirePerm>} />
          <Route path="engagement" element={<Engagement />} />
          <Route path="requests" element={<HRRequests />} />
          <Route path="cases" element={<RequirePerm any={['people.case.view']}><HRCases /></RequirePerm>} />
          <Route path="lifecycle" element={<RequirePerm any={['people.lifecycle.view', 'people.offboarding.view']}><Lifecycle /></RequirePerm>} />
          <Route path="analytics" element={<RequirePerm any={['people.analytics.view']}><HRAnalytics /></RequirePerm>} />
          <Route path="settings" element={<RequirePerm any={['people.settings.view', 'people.settings.configure']}><HRSettings /></RequirePerm>} />
          <Route path=":id" element={<Profile360 />} />
        </Route>
        <Route path="/m/:key" element={<InShell><ModulePage /></InShell>} />
        <Route path="/help" element={<InShell><HelpPage /></InShell>} />

        <Route path="/settings" element={<InShell><SettingsLayout /></InShell>}>
          <Route index element={<Navigate to="preferences" replace />} />
          <Route path="preferences" element={<PreferencesPage />} />
          <Route path="security" element={<SecurityPage />} />
          <Route path="organization" element={<RequirePerm any={['organization.unit.view']}><OrganizationPage /></RequirePerm>} />
          <Route path="users" element={<RequirePerm any={['identity.user.view']}><UsersPage /></RequirePerm>} />
          <Route path="users/:id" element={<RequirePerm any={['identity.user.view']}><UserDetailPage /></RequirePerm>} />
          <Route path="roles" element={<RequirePerm any={['access.role.view']}><RolesPage /></RequirePerm>} />
          <Route path="roles/:id" element={<RequirePerm any={['access.role.view']}><RoleDetailPage /></RequirePerm>} />
          <Route path="workflows" element={<RequirePerm any={['workflows.policy.view']}><WorkflowsPage /></RequirePerm>} />
          <Route path="audit" element={<RequirePerm any={['audit.event.view']}><AuditPage /></RequirePerm>} />
          <Route path="system" element={<RequirePerm any={['system.health.view']}><SystemPage /></RequirePerm>} />
          <Route path="integrations" element={<RequirePerm any={['integrations.integration.view']}><IntegrationsPage /></RequirePerm>} />
        </Route>

        <Route path="*" element={status === 'signed_in' ? <InShell><NotFound /></InShell> : <Navigate to="/login" replace />} />
      </Routes>
    </Suspense>
  );
}

function NotFound() {
  return (
    <div className="page-state">
      <Empty icon="search" title="Page not found" message="This address doesn’t exist in Click Business OS, or it moved." />
    </div>
  );
}
