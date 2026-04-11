/**
 * Sidebar — M3 Navigation Rail redesign.
 * 80px width, icon + label always visible,
 * 56×32px pill active indicator behind icon.
 */
// @ts-nocheck
import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Network, LayoutGrid,
  Shield, PlugZap, Activity, BarChart2,
  ClipboardList, Settings, LogOut,
  Sun, Moon, Bell, Layers
} from 'lucide-react'
import { NotificationCenter } from './NotificationCenter'
import { useAuth } from './AuthProvider'
import './Sidebar.css'

// ── Theme toggle hook ──────────────────────────────────────────────────────────
function useTheme() {
  const current = document.documentElement.getAttribute('data-theme') ?? 'dark'

  const toggle = () => {
    const next = current === 'dark' ? 'light' : 'dark'
    document.documentElement.setAttribute('data-theme', next)
    localStorage.setItem('dgraph-theme', next)
    // Force re-render — simple event dispatch
    window.dispatchEvent(new CustomEvent('dgraph-theme-change', { detail: next }))
  }

  return { theme: current, toggle }
}

// ── Nav items ──────────────────────────────────────────────────────────────────
const NAV_PRIMARY = [
  { to: '/',           icon: LayoutDashboard, label: 'Dashboard'  },
  { to: '/explore',    icon: Network,         label: 'Explore'    },
  { to: '/inventory',  icon: LayoutGrid,      label: 'Inventory'  },
  { to: '/security',   icon: Shield,          label: 'Security'   },
  { to: '/connectors', icon: PlugZap,         label: 'Connectors' },
  { to: '/agents',     icon: Server,        label: 'Agents'      },
]

const NAV_SECONDARY = [
  { to: '/indexer', icon: Activity,      label: 'Indexer'  },
  { to: '/usage',   icon: BarChart2,     label: 'Usage'    },
  { to: '/audit',   icon: ClipboardList, label: 'Audit'    },
]

// ── Main component ─────────────────────────────────────────────────────────────
export function Sidebar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { theme, toggle } = useTheme()

  const initials = user
    ? (user.name || user.email).split(' ').map((w: string) => w[0]).join('').slice(0, 2).toUpperCase()
    : '??'

  return (
    <aside className="sidebar" role="navigation" aria-label="Main">

      {/* Logo */}
      <button
        onClick={() => navigate('/')}
        className="sidebar-logo"
        title="dgraph.ai home"
        aria-label="dgraph.ai home"
      >
        <Layers size={16} />
        <span className="sidebar-logo-label">dgraph</span>
      </button>

      {/* Primary nav */}
      <nav className="sidebar-nav sidebar-nav-primary" aria-label="Primary">
        {NAV_PRIMARY.map(({ to, icon: Icon, label }) => (
          <SidebarItem key={to} to={to} icon={Icon} label={label} exact={to === '/'} />
        ))}
      </nav>

      <div className="sidebar-divider" role="separator" />

      {/* Secondary nav */}
      <nav className="sidebar-nav" aria-label="Secondary">
        {NAV_SECONDARY.map(({ to, icon: Icon, label }) => (
          <SidebarItem key={to} to={to} icon={Icon} label={label} />
        ))}
      </nav>

      <div className="sidebar-spacer" />

      {/* Theme toggle */}
      <button
        onClick={toggle}
        className="sidebar-bottom-btn"
        title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        aria-label={theme === 'dark' ? 'Light mode' : 'Dark mode'}
      >
        {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        <span className="sidebar-item-label">{theme === 'dark' ? 'Light' : 'Dark'}</span>
      </button>

      {/* Notifications */}
      <div className="sidebar-bottom-btn sidebar-notif-wrap" title="Notifications">
        <NotificationCenter />
        <span className="sidebar-item-label">Alerts</span>
      </div>

      {/* Settings */}
      <NavLink to="/settings" className={({ isActive }) =>
        `sidebar-bottom-btn ${isActive ? 'active' : ''}`
      } title="Settings">
        <Settings size={16} />
        <span className="sidebar-item-label">Settings</span>
      </NavLink>

      {/* Avatar */}
      <button
        onClick={() => navigate('/settings')}
        className="sidebar-avatar"
        title={user ? `${user.name || user.email}` : 'Account'}
        aria-label="Account settings"
      >
        {initials}
      </button>

      {/* Logout */}
      <button
        onClick={logout}
        className="sidebar-bottom-btn sidebar-logout"
        title="Sign out"
        aria-label="Sign out"
      >
        <LogOut size={15} />
        <span className="sidebar-item-label">Logout</span>
      </button>

    </aside>
  )
}

// ── Nav item ───────────────────────────────────────────────────────────────────
function SidebarItem({
  to, icon: Icon, label, exact = false,
}: {
  to: string; icon: any; label: string; exact?: boolean
}) {
  return (
    <NavLink
      to={to}
      end={exact}
      title={label}
      aria-label={label}
      className={({ isActive }) => `sidebar-item${isActive ? ' active' : ''}`}
    >
      <div className="sidebar-item-indicator">
        <Icon size={18} />
      </div>
      <span className="sidebar-item-label">{label}</span>
    </NavLink>
  )
}


