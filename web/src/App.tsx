// @ts-nocheck
import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Sidebar }      from './components/Sidebar'
import { AuthProvider } from './components/AuthProvider'
import { AuthGuard }    from './components/AuthGuard'

// ── Auth pages — loaded immediately (small, needed before app shell) ──────────
import { LoginPage }          from './pages/auth/LoginPage'
import { SignupPage }         from './pages/auth/SignupPage'
import { ForgotPasswordPage } from './pages/auth/ForgotPasswordPage'
import { ResetPasswordPage }  from './pages/auth/ResetPasswordPage'
import { AcceptInvitePage }   from './pages/auth/AcceptInvitePage'

// ── Heavy pages — lazy loaded (Cytoscape, React Flow, CodeMirror) ─────────────
const GraphPage        = lazy(() => import('./pages/GraphPage').then(m => ({ default: m.GraphPage })))
const QueryWorkspace   = lazy(() => import('./pages/QueryWorkspace').then(m => ({ default: m.QueryWorkspace })))
const QueryBuilder     = lazy(() => import('./pages/QueryBuilder').then(m => ({ default: m.QueryBuilder })))
const WorkflowBuilder  = lazy(() => import('./pages/WorkflowBuilder'))
const SecurityPage     = lazy(() => import('./pages/SecurityPage').then(m => ({ default: m.SecurityPage })))
const IndexerDashboard = lazy(() => import('./pages/IndexerDashboard').then(m => ({ default: m.IndexerDashboard })))

// ── Light pages — lazy loaded ─────────────────────────────────────────────────
const MountsPage       = lazy(() => import('./pages/MountsPage').then(m => ({ default: m.MountsPage })))
const ConnectorsPage   = lazy(() => import('./pages/ConnectorsPage').then(m => ({ default: m.ConnectorsPage })))
const InventoryPage    = lazy(() => import('./pages/InventoryPage').then(m => ({ default: m.InventoryPage })))
const UsagePage        = lazy(() => import('./pages/UsagePage').then(m => ({ default: m.UsagePage })))
const SettingsPage     = lazy(() => import('./pages/SettingsPage').then(m => ({ default: m.SettingsPage })))
const AuditLogPage     = lazy(() => import('./pages/AuditLogPage').then(m => ({ default: m.AuditLogPage })))
const GraphDiffPage    = lazy(() => import('./pages/GraphDiffPage').then(m => ({ default: m.GraphDiffPage })))
const NotFoundPage     = lazy(() => import('./pages/NotFoundPage').then(m => ({ default: m.NotFoundPage })))
const LegalPage        = lazy(() => import('./pages/LegalPage').then(m => ({ default: m.LegalPage })))
const VerifyEmailPage  = lazy(() => import('./pages/auth/VerifyEmailPage').then(m => ({ default: m.VerifyEmailPage })))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 10_000, retry: 1 },
  },
})

const AUTH_ONLY_PATHS = [
  '/login', '/signup', '/forgot-password', '/reset-password',
  '/verify-email', '/accept-invite',
]

// ── Loading fallback ──────────────────────────────────────────────────────────
function PageLoader() {
  return (
    <div style={{
      flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: '#0a0a0f',
    }}>
      <div style={{
        width: 32, height: 32, borderRadius: '50%',
        border: '3px solid #1a1a28', borderTopColor: '#4f8ef7',
        animation: 'spin .7s linear infinite',
      }} />
    </div>
  )
}

// ── Settings placeholder (still loading) ──────────────────────────────────────
function PlaceholderPage({ title, desc }: { title: string; desc: string }) {
  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0a0a0f' }}>
      <div style={{ textAlign: 'center' }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: '#e2e2f0' }}>{title}</h2>
        <p style={{ fontSize: 12, color: '#55557a', marginTop: 4 }}>{desc}</p>
      </div>
    </div>
  )
}

function AppShell() {
  const location = useLocation()
  const isAuthPage = AUTH_ONLY_PATHS.some(p => location.pathname.startsWith(p))

  return (
    <div className="flex h-screen overflow-hidden">
      {!isAuthPage && <Sidebar />}
      <main className="flex-1 flex flex-col overflow-hidden">
        <Suspense fallback={<PageLoader />}>
          <Routes>
            {/* Auth — not lazy, needed immediately */}
            <Route path="/login"           element={<LoginPage />} />
            <Route path="/signup"          element={<SignupPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password"  element={<ResetPasswordPage />} />
            <Route path="/accept-invite"   element={<AcceptInvitePage />} />
            <Route path="/verify-email"    element={<VerifyEmailPage />} />
            <Route path="/legal/:type"     element={<LegalPage />} />
            <Route path="/terms"           element={<LegalPage />} />
            <Route path="/privacy"         element={<LegalPage />} />

            {/* App routes — lazy */}
            <Route path="/"           element={<GraphPage />} />
            <Route path="/mounts"     element={<MountsPage />} />
            <Route path="/connectors" element={<ConnectorsPage />} />
            <Route path="/inventory"  element={<InventoryPage />} />
            <Route path="/builder"    element={<QueryBuilder />} />
            <Route path="/query"      element={<QueryWorkspace />} />
            <Route path="/security"   element={<SecurityPage />} />
            <Route path="/workflows"  element={<WorkflowBuilder />} />
            <Route path="/indexer"    element={<IndexerDashboard />} />
            <Route path="/usage"      element={<UsagePage />} />
            <Route path="/settings"   element={<SettingsPage />} />
            <Route path="/audit"      element={<AuditLogPage />} />
            <Route path="/diff"       element={<GraphDiffPage />} />
            <Route path="*"           element={<NotFoundPage />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <AuthGuard>
            <AppShell />
          </AuthGuard>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
