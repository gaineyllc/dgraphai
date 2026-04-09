import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Sidebar } from './components/Sidebar'
import { GraphPage } from './pages/GraphPage'
import { MountsPage } from './pages/MountsPage'
import { QueryWorkspace } from './pages/QueryWorkspace'
import WorkflowBuilderPage from './pages/WorkflowBuilder'
import { IndexerDashboard } from './pages/IndexerDashboard'
import { SecurityPage }     from './pages/SecurityPage'
import { ConnectorsPage }   from './pages/ConnectorsPage'
import { InventoryPage }    from './pages/InventoryPage'
import { QueryBuilder }     from './pages/QueryBuilder'
import { UsagePage }       from './pages/UsagePage'
import { LoginPage }          from './pages/auth/LoginPage'
import { SignupPage }         from './pages/auth/SignupPage'
import { ForgotPasswordPage }  from './pages/auth/ForgotPasswordPage'
import { ResetPasswordPage }   from './pages/auth/ResetPasswordPage'
import { SettingsPage }        from './pages/SettingsPage'
import { useQuery } from '@tanstack/react-query'
import { graphApi } from './lib/api'
import { Terminal, Shield, Activity, Settings } from 'lucide-react'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 10_000, retry: 1 },
  },
})

function AppShell() {
  const { data: stats } = useQuery({
    queryKey: ['graph-stats'],
    queryFn: graphApi.stats,
    refetchInterval: 30_000,
  })

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 flex flex-col overflow-hidden">
        <Routes>
          <Route path="/"         element={<GraphPage />} />
          <Route path="/mounts"     element={<MountsPage />} />
          <Route path="/connectors" element={<ConnectorsPage />} />
          <Route path="/inventory"  element={<InventoryPage />} />
          <Route path="/builder"    element={<QueryBuilder />} />
          <Route path="/usage"      element={<UsagePage />} />
          <Route path="/login"     element={<LoginPage />} />
          <Route path="/signup"    element={<SignupPage />} />
          <Route path="/forgot-password"  element={<ForgotPasswordPage />} />
          <Route path="/reset-password"   element={<ResetPasswordPage />} />
          <Route path="/settings"         element={<SettingsPage />} />
          <Route path="/query"    element={<QueryWorkspace />} />
          <Route path="/security" element={<SecurityPage />} />
          <Route path="/workflows" element={<WorkflowBuilderPage />} />
          <Route path="/indexer"  element={<IndexerDashboard />} />
          <Route path="/settings" element={<PlaceholderPage icon={Settings} title="Settings"             desc="Configure fsgraph" />} />
        </Routes>
      </main>
    </div>
  )
}

function PlaceholderPage({ icon: Icon, title, desc }: {
  icon: React.ElementType
  title: string
  desc: string
}) {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center">
        <div className="w-14 h-14 rounded-2xl bg-[#12121a] border border-[#252535] flex items-center justify-center mx-auto mb-4">
          <Icon size={24} className="text-[#4f8ef7]" />
        </div>
        <h2 className="text-lg font-semibold text-[#e2e2f0]">{title}</h2>
        <p className="text-sm text-[#55557a] mt-1">{desc}</p>
        <p className="text-xs text-[#252535] mt-4">Coming next session</p>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    </QueryClientProvider>
  )
}
