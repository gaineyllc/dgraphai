/**
 * Sidebar — navigation with user account section.
 */
// @ts-nocheck
import { NavLink, useNavigate } from 'react-router-dom'
import {
  Network, HardDrive, Terminal,
  Shield, Activity, Settings, Layers, PlugZap,
  LayoutGrid, Wrench, BarChart2, ClipboardList,
  LogOut, Search, GitCompare
} from 'lucide-react'
import { GlobalSearch } from './GlobalSearch'
import { useAuth } from './AuthProvider'

const NAV = [
  { to: '/',           icon: Network,       label: 'Graph'      },
  { to: '/mounts',     icon: HardDrive,     label: 'Sources'    },
  { to: '/connectors', icon: PlugZap,       label: 'Connectors' },
  { to: '/inventory',  icon: LayoutGrid,    label: 'Inventory'  },
  { to: '/query',      icon: Terminal,      label: 'Query'      },
  { to: '/builder',    icon: Wrench,        label: 'Builder'    },
  { to: '/security',   icon: Shield,        label: 'Security'   },
  { to: '/indexer',    icon: Activity,      label: 'Indexer'    },
  { to: '/usage',      icon: BarChart2,     label: 'Usage'      },
  { to: '/audit',      icon: ClipboardList, label: 'Audit Log'  },
  { to: '/diff',       icon: GitCompare,    label: 'What Changed'},
]

export function Sidebar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const initials = user
    ? (user.name || user.email).split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
    : '??'

  return (
    <aside className="w-14 flex flex-col items-center bg-[#12121a] border-r border-[#252535] py-3 gap-1 flex-shrink-0">

      {/* Logo — click to go home */}
      <button
        onClick={() => navigate('/')}
        className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#4f8ef7] to-[#8b5cf6] flex items-center justify-center mb-2 hover:opacity-90 transition-opacity"
        title="dgraph.ai"
      >
        <Layers size={16} className="text-white" />
      </button>

      {/* Global search */}
      <div className="w-10 mb-1"><GlobalSearch /></div>

      {/* Nav items */}
      {NAV.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          title={label}
          className={({ isActive }) =>
            `w-10 h-10 rounded-lg flex items-center justify-center transition-colors group relative ` +
            (isActive
              ? 'bg-[#4f8ef7]/20 text-[#4f8ef7]'
              : 'text-[#55557a] hover:text-[#e2e2f0] hover:bg-[#1a1a28]')
          }
        >
          <Icon size={18} />
          <span className="absolute left-full ml-2 px-2 py-1 bg-[#1a1a28] border border-[#252535] text-[#e2e2f0] text-xs rounded whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none z-50 transition-opacity">
            {label}
          </span>
        </NavLink>
      ))}

      <div className="flex-1" />

      {/* Settings */}
      <NavLink to="/settings" title="Settings"
        className={({ isActive }) =>
          `w-10 h-10 rounded-lg flex items-center justify-center transition-colors ` +
          (isActive ? 'bg-[#4f8ef7]/20 text-[#4f8ef7]' : 'text-[#55557a] hover:text-[#e2e2f0] hover:bg-[#1a1a28]')
        }>
        <Settings size={18} />
      </NavLink>

      {/* User avatar → settings on click */}
      <button
        onClick={() => navigate('/settings')}
        title={user ? `${user.name || user.email}\n${user.plan} plan` : 'Account'}
        className="w-8 h-8 rounded-full bg-[#4f8ef7] text-white text-xs font-bold flex items-center justify-content mt-1 hover:opacity-90 transition-opacity"
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      >
        {initials}
      </button>

      {/* Logout */}
      <button
        onClick={logout}
        title="Sign out"
        className="w-10 h-8 rounded-lg flex items-center justify-center text-[#35354a] hover:text-[#f87171] hover:bg-[#1a1a28] transition-colors mb-1"
      >
        <LogOut size={15} />
      </button>
    </aside>
  )
}
