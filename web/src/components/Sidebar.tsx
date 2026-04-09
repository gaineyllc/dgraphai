/**
 * Sidebar — Material 3 Expressive icon rail navigation.
 * Electric indigo active state, tonal surfaces, M3 state layers.
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
import { NotificationCenter } from './NotificationCenter'
import { useAuth } from './AuthProvider'
import './Sidebar.css'

const NAV_PRIMARY = [
  { to: '/',           icon: Network,       label: 'Graph'        },
  { to: '/inventory',  icon: LayoutGrid,    label: 'Inventory'    },
  { to: '/security',   icon: Shield,        label: 'Security'     },
  { to: '/diff',       icon: GitCompare,    label: 'What Changed' },
  { to: '/connectors', icon: PlugZap,       label: 'Connectors'   },
]

const NAV_SECONDARY = [
  { to: '/query',      icon: Terminal,      label: 'Query'        },
  { to: '/builder',    icon: Wrench,        label: 'Builder'      },
  { to: '/indexer',    icon: Activity,      label: 'Indexer'      },
  { to: '/usage',      icon: BarChart2,     label: 'Usage'        },
  { to: '/audit',      icon: ClipboardList, label: 'Audit Log'    },
  { to: '/mounts',     icon: HardDrive,     label: 'Sources'      },
]

export function Sidebar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const initials = user
    ? (user.name || user.email).split(' ').map((w: string) => w[0]).join('').slice(0, 2).toUpperCase()
    : '??'

  return (
    <aside className="sidebar">
      {/* Logo */}
      <button
        onClick={() => navigate('/')}
        className="sidebar-logo"
        title="dgraph.ai"
        aria-label="dgraph.ai home"
      >
        <Layers size={17} />
      </button>

      {/* Global search */}
      <div className="sidebar-search">
        <GlobalSearch />
      </div>

      {/* Primary nav */}
      <nav className="sidebar-nav" role="navigation" aria-label="Primary">
        {NAV_PRIMARY.map(({ to, icon: Icon, label }) => (
          <SidebarItem key={to} to={to} icon={Icon} label={label} />
        ))}
      </nav>

      <div className="sidebar-divider" role="separator" />

      {/* Secondary nav */}
      <nav className="sidebar-nav" role="navigation" aria-label="Secondary">
        {NAV_SECONDARY.map(({ to, icon: Icon, label }) => (
          <SidebarItem key={to} to={to} icon={Icon} label={label} />
        ))}
      </nav>

      <div className="sidebar-spacer" />

      {/* Notifications */}
      <div className="sidebar-action">
        <NotificationCenter />
      </div>

      {/* Settings */}
      <NavLink to="/settings" title="Settings" className="sidebar-action-link">
        {({ isActive }) => (
          <div className={`sidebar-item ${isActive ? 'active' : ''}`}>
            <Settings size={18} />
            <span className="sidebar-tooltip">Settings</span>
          </div>
        )}
      </NavLink>

      {/* User avatar */}
      <button
        onClick={() => navigate('/settings')}
        title={user ? `${user.name || user.email}\n${user.plan ?? 'free'} plan` : 'Account'}
        className="sidebar-avatar"
        aria-label="Account settings"
      >
        {initials}
      </button>

      {/* Logout */}
      <button
        onClick={logout}
        title="Sign out"
        className="sidebar-item sidebar-logout"
        aria-label="Sign out"
      >
        <LogOut size={15} />
      </button>
    </aside>
  )
}

function SidebarItem({ to, icon: Icon, label }: { to: string; icon: any; label: string }) {
  return (
    <NavLink
      to={to}
      title={label}
      className={({ isActive }) => `sidebar-item ${isActive ? 'active' : ''}`}
      aria-label={label}
    >
      <Icon size={18} />
      <span className="sidebar-tooltip">{label}</span>
    </NavLink>
  )
}
