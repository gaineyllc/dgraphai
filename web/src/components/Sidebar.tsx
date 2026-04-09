/**
 * Sidebar — navigation + stats overview.
 */
import { NavLink } from 'react-router-dom'
import {
  Network, Search, HardDrive, Terminal,
  Shield, Activity, Settings, Layers, PlugZap,
  LayoutGrid, Wrench, BarChart2
} from 'lucide-react'

const NAV = [
  { to: '/',        icon: Network,    label: 'Graph'      },
  { to: '/search',  icon: Search,     label: 'Search'     },
  { to: '/mounts',     icon: HardDrive, label: 'Sources'    },
  { to: '/connectors', icon: PlugZap,    label: 'Connectors' },
  { to: '/inventory',  icon: LayoutGrid, label: 'Inventory'  },
  { to: '/builder',    icon: Wrench,     label: 'Builder'    },
  { to: '/usage',      icon: BarChart2,  label: 'Usage'      },
  { to: '/query',      icon: Terminal,   label: 'Query'      },
  { to: '/security',icon: Shield,     label: 'Security'   },
  { to: '/indexer', icon: Activity,   label: 'Indexer'    },
]

interface Props {}

export function Sidebar({}: Props) {
  return (
    <aside className="w-14 flex flex-col items-center bg-[#12121a] border-r border-[#252535] py-3 gap-1 flex-shrink-0">
      {/* Logo */}
      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#4f8ef7] to-[#8b5cf6] flex items-center justify-center mb-3">
        <Layers size={16} className="text-white" />
      </div>

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
          {/* Tooltip */}
          <span className="absolute left-full ml-2 px-2 py-1 bg-[#1a1a28] border border-[#252535] text-[#e2e2f0] text-xs rounded whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none z-50 transition-opacity">
            {label}
          </span>
        </NavLink>
      ))}

      <div className="flex-1" />

      <NavLink
        to="/settings"
        title="Settings"
        className={({ isActive }) =>
          `w-10 h-10 rounded-lg flex items-center justify-center transition-colors ` +
          (isActive
            ? 'bg-[#4f8ef7]/20 text-[#4f8ef7]'
            : 'text-[#55557a] hover:text-[#e2e2f0] hover:bg-[#1a1a28]')
        }
      >
        <Settings size={18} />
      </NavLink>
    </aside>
  )
}
