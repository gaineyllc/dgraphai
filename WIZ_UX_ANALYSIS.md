# Wiz UX Analysis & dgraph.ai Gap Report

> Generated April 2026 — based on 15 Wiz demo screenshots + dgraph.ai codebase review

---

## 1. Summary of All 15 Wiz Screenshots

### Screenshot 1 — Platform Overview Dashboard (`PXL_20260409_204108347`)
The main landing page. Three-column card grid across the top (Threats, Risk Issues, Posture Issues) with secondary widgets below (Incident Readiness, Security Score, Sensor Coverage, Subscriptions). Large bold numerals are the visual focal point; each metric has a colored delta badge (↑↓ % change). The Security Score widget shows a gauge at 49% with a Financial Services industry benchmark overlay. A "Mika AI" assistant button floats in the bottom-right of the dashboard area. Left nav is icon-only rail with Wiz teal-blue accent on active items.

### Screenshot 2 — Boards Flyout Navigation (`PXL_20260409_204120940`)
Boards section with secondary flyout panel open, showing "Recent" and "Managed by Wiz" grouped board lists. The flyout slides out from the narrow icon sidebar, revealing labeled board options with a blue highlight on the active item. The main content remains partially visible behind, preserving context. The Security Score gauge (49%) with industry benchmark is again prominent.

### Screenshot 3 — Boards Flyout (Wide View) (`PXL_20260409_204126266`)
Essentially same as #2 but wider angle. Confirms the two-level nav model: icon sidebar → labeled flyout panel → content. Percentage-change indicators with colored arrows (↓93%, ↑6%) are very readable. The gauge uses amber/gold at 49% — clearly a warning color, not green.

### Screenshot 4 — Issues Flyout Navigation (`PXL_20260409_204131596`)
Issues section flyout revealing subcategories: Risk Issues and Posture Issues. Standard traffic-light severity coding throughout — **C** red / **H** orange / **M** yellow / **L** gray — applied consistently across all metric cards. The delta badges and the gauge benchmark appear on every dashboard-context view.

### Screenshot 5 — Findings Navigation Panel (`PXL_20260409_204136234`)
Findings flyout expanded, showing five top-level finding groups: Security Posture, Threat Detection, Secure Development, Cloud Ops, Asset Management. Category headers use small uppercase gray labels (section dividers). The hierarchical grouping makes a deep navigation catalog scannable at a glance.

### Screenshot 6 — Inventory Flyout Navigation (`PXL_20260409_204139866`)
Inventory section flyout with collapsible sub-groups (Technologies, Cloud Resources, Infrastructure, Access & Identity, Software Assets, Network, Code & Development). Chevron toggles for expandable groups. The Security Score gauge with benchmark stays visible in the background content pane — reinforcing the persistent dashboard context.

### Screenshot 7 — Inventory › Technologies List (`PXL_20260409_204148980`)
Full-page Inventory view for Technologies (810 items). Three-panel breakdown at top: by Category (donut chart), Subcategory, and Type. Below: scrollable data table with columns for Resources, Type, Org. Usage, Status. Active filter shown as a pill chip ("Detected in Environment equals True"). Category/Type dropdown filters inline. Left sidebar collapses to icon+label, slightly wider than the rail-only mode shown elsewhere.

### Screenshot 8 — Inventory › Technologies / Log4j Search (`PXL_20260409_204200721`)
Same page filtered with "log4j" search — surfaces Apache Log4j across 40 resources. Demonstrates shareable/bookmarkable filter state via URL-encoded query params. The breakdown panels dynamically reflect the filtered result set. Yellow/amber icons for Frameworks & Libraries category provide instant visual categorization.

### Screenshot 9 — Explorer Navigation Flyout (`PXL_20260409_204205936`)
Explorer section flyout showing sub-pages: Security Graph, Cloud Events, Runtime Events, Network Graph, Identity Entitlements, Cost. Progressive disclosure maintained — the flyout only appears on interaction, keeping default chrome minimal. The Technologies breakdown panel stays visible in background content.

### Screenshot 10 — Security Graph (Attack Path Visualization) (`PXL_20260409_204212273`)
The flagship graph view — a node-link visualization mapping a full RCE attack path from the Internet through application endpoints to AI infrastructure (DataBot, Claude Sonnet) and RDS findings. Left-to-right flow with circular icon nodes on a white canvas. Color semantics: red/coral = high-severity/attack surface, blue = AI/cloud services, green = data resources, orange = exposed endpoints. A "Validated External Risk" badge in red pill style overlays the critical node. Mika AI button + zoom controls + Lens feature in bottom-right corner. Top toolbar offers View/Table/Graph toggle.

### Screenshot 11 — Security Graph (Node Detail Slide-Over) (`PXL_20260409_204218226`)
Graph with a right-side detail panel for a selected node (internet-exposed endpoint `18.188.230.150:80/execute_tool`). Panel shows: Highlights (risk badges with icons), External ID, Subscription, and a "View Details" CTA button. Red/pink risk nodes vs blue infrastructure nodes visible. Highlights section uses iconized risk badges (Validated Public Network Exposure, Browser Screenshot). Notably surfaces AI-specific infrastructure nodes (DataBot Hosted AI Agent, US Claude Bedrock) — Wiz's AISP positioning.

### Screenshot 12 — Security Graph (Full Node Detail Panel, Tabbed) (`PXL_20260409_204225192`)
Full detail panel for the same endpoint. Tabbed navigation across: Overview, Ownership, Threats, Risk, Governance, Ops. Orange/red severity badges and a yellow "Medium" exposure badge visible. **Attack Surface Scanner Insights** section shows live HTTP response data inline (raw JSON 401 UNAUTHORIZED displayed directly), making actionable evidence immediately visible without leaving context. Slide-over preserves graph visibility to the left.

### Screenshot 13 — Settings Flyout (over Graph) (`PXL_20260409_204234761`)
Settings menu as overlay panel on top of the Security Graph. Flat, scrollable list with chevron (›) indicators for expandable sub-menus: Access Management, Scanners, Events, Logs, etc. The Security Graph remains visible and context-preserving behind the overlay. Demonstrates consistent overlay/panel layering throughout the app.

### Screenshot 14 — Settings › Deployments (`PXL_20260409_204243105`)
Cloud integrations management page. Horizontal tab bar for deployment types (Cloud, Kubernetes, Registry, Sensor, Broker, etc.). Dense data table: Health Issues, Status, Sources, Modules, Last Activity columns. Multi-filter dropdowns (Cloud Platform, Status, Source, Installed Modules, Cloud Type). Green "Active" status badges for quick health scanning. Red/yellow health-issue tags use severity coding. "+ Add Deployment" CTA prominently blue in top-right.

### Screenshot 15 — Settings › Connect (Integration Catalog) (`PXL_20260409_204249197`)
Integration marketplace/catalog. Two-panel layout: left filterable category sidebar with item counts (Cloud 17, Kubernetes 19, Integrations 233) and right grid of integration cards by section (Cloud Service Providers, Data & AI). Full-width search bar at top. Vendor brand logos as card icons. **"Preview" badges** on emerging integrations (Cloudflare, Vercel, IBM Cloud). Mika AI assistant button bottom-right.

---

## 2. Key Wiz UX Patterns

### 2.1 Color & Theme
| Role | Value |
|------|-------|
| **Base theme** | Light (white/`#f9f9f9` content, `#0d1117` sidebar) |
| **Brand accent** | Teal-blue `#4B8BF5` — buttons, active nav, links |
| **Critical severity** | Red (`#ef4444`-range) |
| **High severity** | Orange (`#f97316`-range) |
| **Medium severity** | Yellow (`#eab308`-range) |
| **Low severity** | Gray (`#9ca3af`-range) |
| **Success / Active** | Green (`#22c55e`-range) |
| **Score gauge** | Amber/gold at mid-range scores |
| **AI/cloud nodes** | Blue-purple in graph |
| **Attack/risk nodes** | Coral/red in graph |

The CHML (Critical/High/Medium/Low) color system is applied **everywhere consistently** — badges, left-border accents on panels, node colors in graphs, chart segments, table row highlights.

### 2.2 Typography
- **Font**: System sans-serif (Inter-family weight feel)
- **Hierarchy**: Large bold numerals (36–48px) as primary focal points → medium labels (13px) → small muted metadata (10–11px)
- **ALL CAPS + letter-spacing**: Used extensively for section group headers and column labels
- **Monospace**: Used for paths, IDs, code snippets (inline in detail panels)
- **No decorative type** — purely functional, data-forward

### 2.3 Layout Patterns
- **Navigation model**: Narrow icon rail (56px) → secondary flyout panel → main content. Three distinct layers.
- **Dashboard grid**: `repeat(auto-fill, minmax(~220px, 1fr))` card grid with summary metric cards at top, secondary widgets below
- **Flyout panels**: Triggered by nav item hover/click, slide in over content, preserve background context
- **Slide-over detail panels**: Right-anchored (~400px), triggered by graph node selection or table row click, tabbed
- **Data tables**: Dense, sticky headers, row hover, column filters in toolbar above
- **Integration catalog**: Two-column layout — filterable left sidebar + card grid

### 2.4 Components of Note
| Component | Description |
|-----------|-------------|
| **Metric card** | Icon + large number + delta badge (↑↓ %) + label |
| **CHML badge** | Pill with C/H/M/L letter + color fill |
| **Delta/trend badge** | Colored arrow + percentage, green=good, red=bad |
| **Security Score gauge** | Radial gauge + needle + benchmark overlay line |
| **Filter pill** | Rounded chip showing active filter; can be dismissed |
| **Nav flyout** | Secondary panel with grouped, labeled nav items + counts |
| **Graph node** | Circle + icon + label below + color by severity role |
| **Detail tab strip** | Overview / Ownership / Threats / Risk / Governance / Ops |
| **Inline evidence** | Raw HTTP responses, screenshots shown directly in detail panels |
| **Preview badge** | Yellow pill on emerging/beta integrations |
| **AI assistant button** | Floating bottom-right, persistent across all pages |

### 2.5 Interaction & Motion Patterns
- Flyout panels slide in with `transform: translateX` — short duration, ease-out
- Row hover is subtle `background` tint — no scale transforms
- Graph nodes are draggable, zoomable canvas (Cytoscape-style)
- Filters are URL-encoded — fully bookmarkable/shareable state
- Detail panels preserve graph/list context behind them (no full-page navigation)

---

## 3. Gap Analysis vs dgraph.ai

### 3.1 What dgraph.ai Does Well (Competitive Strengths)
- ✅ Richer color system — HCT-derived indigo primary is more distinctive than Wiz's generic blue
- ✅ Material 3 Expressive design tokens — systematic, scalable, well-documented
- ✅ Dark theme as identity — "black-violet" aesthetic is strongly differentiated
- ✅ NL (natural language) search in Inventory — Wiz doesn't have this
- ✅ Cytoscape graph canvas with context menu and attack path computation
- ✅ Severity badge system (SeverityBadge component) and TrendBadge component exist
- ✅ InspectionPane for graph node detail

### 3.2 Gaps (What Wiz Has That dgraph.ai Lacks or Does Weaker)

| # | Gap | Severity | Notes |
|---|-----|----------|-------|
| G1 | **No overview/home dashboard** | 🔴 Critical | Wiz's landing page has aggregate metric cards with CHML counts, deltas, gauge, and industry benchmark. dgraph.ai has no equivalent. Users land on the graph with no orientation. |
| G2 | **No delta/trend indicators on summary metrics** | 🔴 Critical | TrendBadge component exists but isn't prominently surfaced on any summary view. Wiz puts ↑↓ % on *every* metric card. |
| G3 | **Nav flyout panels missing** | 🟠 High | dgraph.ai's sidebar is icon-only with tooltip labels on hover. Wiz's sidebar expands to a full secondary panel with grouped, labeled sub-navigation. Deep navigation is hidden in dgraph.ai. |
| G4 | **Security Score / Posture Gauge absent** | 🟠 High | Wiz's gauge chart with industry benchmark is a flagship widget. No equivalent in dgraph.ai. |
| G5 | **Detail panel is shallow (single-level)** | 🟠 High | Wiz's graph node detail panel has 6 tabs (Overview, Ownership, Threats, Risk, Governance, Ops) with inline raw evidence. dgraph.ai's InspectionPane appears to be a flat property list. |
| G6 | **Filter pills not used in Inventory** | 🟡 Medium | Wiz surfaces active filters as dismissible pill chips in the main toolbar. dgraph.ai has a filter bar that's toggle-hidden below the list. Filters should be always-visible pills when active. |
| G7 | **No AI assistant surface** | 🟡 Medium | Wiz's Mika AI floating button is present on every page. dgraph.ai has no persistent AI assistant entry point (despite having AI infrastructure). |
| G8 | **Integration catalog UX weaker** | 🟡 Medium | ConnectorsPage exists but likely lacks the two-column category sidebar + count badges + Preview tags that make Wiz's catalog scannable. |
| G9 | **URL filter state not bookmarkable** | 🟡 Medium | Wiz encodes full filter/search state in URL query params. dgraph.ai's state appears to be React-local only. |
| G10 | **No industry/peer benchmarking** | 🟢 Low | Wiz shows "Financial Services average" on the security score gauge. Not feasible without data, but a differentiator worth planning for. |
| G11 | **No "Preview" badge system** | 🟢 Low | Wiz's integration catalog uses yellow Preview badges on emerging integrations — communicates roadmap without committing. Easy to add. |
| G12 | **Graph lacks semantic color roles for node types** | 🟡 Medium | Wiz's graph uses distinct colors per node role (red=attack surface, blue=AI, green=data, orange=exposed). dgraph.ai's graph color system is less semantically structured. |

---

## 4. Prioritized Improvements with CSS/Component Guidance

> Ordered by impact × effort ratio. Start with P1; defer P4.

---

### P1 — Overview Dashboard Page *(New Page)*

**What**: Create an `OverviewPage.tsx` as the default landing route, replacing the graph as home.

**Layout**:
```
┌─────────────────────────────────────────────────────┐
│  Summary Row:  [Critical N ↑X%] [High N] [Medium N] [Low N]  │
├──────────────────────┬──────────────────────────────┤
│  Threats Panel       │  Risk Issues Panel            │
│  (collapsible table) │  (CHML breakdown + delta)     │
├──────────────────────┼──────────────────────────────┤
│  Security Score      │  Top Exposed Assets           │
│  (gauge + trend)     │  (mini table)                 │
└──────────────────────┴──────────────────────────────┘
```

**CSS**:
```css
.overview-page {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-5) var(--space-6) var(--space-12);
  background: var(--surface-0);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ov-summary-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--space-3);
}

.ov-metric-card {
  background: var(--surface-1);
  border: 1px solid var(--border-card);
  border-left: 3px solid var(--c, var(--color-primary));
  border-radius: var(--radius-md);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  transition: border-color var(--duration-fast) var(--ease-standard);
}
.ov-metric-card:hover { border-color: var(--c); }

.ov-metric-number {
  font-size: var(--text-display-md);   /* 28px */
  font-weight: 800;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.ov-metric-label {
  font-size: var(--text-label-sm);     /* 11px */
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-tertiary);
  font-weight: 600;
}

.ov-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
}
@media (max-width: 900px) {
  .ov-grid { grid-template-columns: 1fr; }
}
```

**Component guidance**: Reuse `SeverityBadge`, `TrendBadge`. Add a `<MetricCard severity="critical" value={142} delta={-0.93} label="Critical Issues" />` component that wraps these.

---

### P2 — Trend/Delta Badges on All Summary Metrics *(Enhance Existing)*

**What**: Surface `TrendBadge` prominently on every metric card — not just in detail views.

**CSS** (enhance `TrendBadge.css`):
```css
.trend-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 7px;
  border-radius: var(--radius-full);
  font-size: var(--text-label-sm);    /* 11px */
  font-weight: 700;
  white-space: nowrap;
}
.trend-badge--up-bad {
  background: var(--color-critical-dim);
  color: var(--color-critical);
}
.trend-badge--down-good {
  background: var(--color-success-dim);
  color: var(--color-success);
}
.trend-badge--up-good {
  background: var(--color-success-dim);
  color: var(--color-success);
}
.trend-badge--neutral {
  background: var(--surface-2);
  color: var(--text-tertiary);
}
```

**Usage**: Pass `direction` + `semantics` props so callers control whether up=good or up=bad (severity counts: up is bad; security score: up is good).

---

### P3 — Nav Flyout Secondary Panels *(Enhance Sidebar)*

**What**: Upgrade `Sidebar.tsx` so clicking a nav item opens a labeled flyout panel beside the icon rail — matching Wiz's three-layer navigation model.

**CSS additions to `Sidebar.css`**:
```css
/* Flyout panel */
.sidebar-flyout {
  position: fixed;
  left: var(--sidebar-width);  /* 56px */
  top: 0;
  bottom: 0;
  width: 220px;
  background: var(--surface-2);
  border-right: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  padding: var(--space-3) 0;
  z-index: calc(var(--z-sticky) - 1);
  box-shadow: 4px 0 20px rgba(0,0,0,0.3);
  /* Enter animation */
  animation: flyout-enter var(--duration-fast) var(--ease-emphasized-decel) both;
}
@keyframes flyout-enter {
  from { transform: translateX(-12px); opacity: 0; }
  to   { transform: translateX(0);     opacity: 1; }
}

.sidebar-flyout-section {
  padding: var(--space-2) var(--space-4);
}
.sidebar-flyout-section-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--text-disabled);
  margin-bottom: var(--space-1);
}

.sidebar-flyout-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: 7px var(--space-3);
  border-radius: var(--radius-sm);
  border: none;
  background: none;
  color: var(--text-secondary);
  font-size: var(--text-label-md);   /* 13px */
  cursor: pointer;
  text-align: left;
  text-decoration: none;
  transition: background var(--duration-micro) var(--ease-standard),
              color var(--duration-micro) var(--ease-standard);
}
.sidebar-flyout-item:hover {
  background: var(--state-hover);
  color: var(--text-primary);
}
.sidebar-flyout-item.active {
  background: var(--color-primary-container);
  color: var(--color-primary-bright);
}

.sidebar-flyout-count {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-disabled);
  font-variant-numeric: tabular-nums;
}
```

**Component**: Create `SidebarFlyout.tsx` accepting `sections: { label: string; items: NavItem[] }[]`. Mount it with `<AnimatePresence>` from framer-motion for clean enter/exit. Click outside or clicking the same icon again dismisses it.

---

### P4 — Active Filter Pills in Inventory Toolbar *(Enhance FilterSidebar)*

**What**: When filters are active, show them as dismissible pill chips in the toolbar above the results — always visible, not hidden behind a toggle.

**CSS**:
```css
.filter-pills-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding: var(--space-2) 0;
}

.filter-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 4px 10px;
  background: color-mix(in srgb, var(--color-primary) 10%, transparent);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-full);
  font-size: var(--text-label-sm);   /* 11px */
  color: var(--color-primary-bright);
  white-space: nowrap;
}

.filter-pill-dismiss {
  background: none;
  border: none;
  color: var(--color-primary-bright);
  cursor: pointer;
  padding: 0;
  display: flex;
  align-items: center;
  opacity: 0.7;
  transition: opacity var(--duration-micro) var(--ease-standard);
}
.filter-pill-dismiss:hover { opacity: 1; }

.filter-pills-clear-all {
  font-size: var(--text-label-sm);
  color: var(--text-tertiary);
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: var(--radius-xs);
  transition: color var(--duration-micro) var(--ease-standard);
}
.filter-pills-clear-all:hover { color: var(--color-critical); }
```

**Usage**: In `InventoryPage.tsx`, render `<FilterPillsRow filters={activeFilters} onDismiss={removeFilter} onClearAll={clearAllFilters} />` above the results table whenever `activeFilters.length > 0`.

---

### P5 — Enhanced Graph Node Semantic Color System *(Enhance GraphCanvas)*

**What**: Apply Wiz-style semantic color roles to graph nodes so node type is instantly readable without reading the label.

**Color role mapping** (add to `tokens.css` or `GraphCanvas.tsx` style config):
```css
/* Graph node color roles — add to tokens.css */
--graph-node-attack:    var(--color-critical-vivid);    /* #f04545 — attacker/internet */
--graph-node-exposed:   var(--color-high);              /* #f97316 — public endpoints */
--graph-node-compute:   #4f8ef7;                        /* blue — EC2, pods, services */
--graph-node-data:      var(--color-success);           /* #34d399 — RDS, storage, secrets */
--graph-node-identity:  var(--color-secondary);         /* teal — IAM, roles, users */
--graph-node-ai:        var(--color-primary);           /* indigo — AI agents, models */
--graph-node-network:   #a78bfa;                        /* purple — VPC, subnets */
--graph-node-unknown:   var(--text-disabled);           /* gray — unclassified */
```

**In Cytoscape style config** (`GraphCanvas.tsx`):
```js
{
  selector: 'node[role="compute"]',
  style: { 'background-color': 'var(--graph-node-compute)' }
},
{
  selector: 'node[role="attack_surface"]',
  style: {
    'background-color': 'var(--graph-node-attack)',
    'border-width': 3,
    'border-color': 'var(--color-critical)'
  }
},
// etc. per role
```

Also add a **graph legend** widget (collapsible, bottom-left of canvas) showing each role → color mapping.

---

### P6 — Tabbed InspectionPane *(Enhance InspectionPane)*

**What**: Add a tab strip to `InspectionPane` so node detail organizes into Overview / Risk / Relationships / Raw — matching Wiz's depth without overwhelming the default view.

**CSS** (add to `inspection.css`):
```css
.insp-tab-strip {
  display: flex;
  border-bottom: 1px solid var(--border-subtle);
  padding: 0 var(--space-4);
  gap: var(--space-1);
  flex-shrink: 0;
}

.insp-tab {
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-label-sm);     /* 11px */
  font-weight: 600;
  color: var(--text-tertiary);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  white-space: nowrap;
  transition: color var(--duration-micro) var(--ease-standard),
              border-color var(--duration-micro) var(--ease-standard);
  margin-bottom: -1px;
}
.insp-tab:hover { color: var(--text-secondary); }
.insp-tab.active {
  color: var(--color-primary-bright);
  border-bottom-color: var(--color-primary);
}
```

**Tab content**: 
- **Overview** — node name, type, key properties, severity badges
- **Risk** — attack paths that pass through this node, CHML findings
- **Relationships** — neighbors list (what connects to/from it)
- **Raw** — all properties in a monospace key-value table

---

### P7 — Persistent AI Assistant Entry Point *(New Component)*

**What**: Add a floating AI query button (similar to Wiz's Mika AI) that opens a slide-over chat/query surface — leveraging dgraph.ai's existing AI graph query capabilities.

**CSS**:
```css
.ai-fab {
  position: fixed;
  bottom: var(--space-5);
  right: var(--space-5);
  z-index: var(--z-overlay);
  width: 48px;
  height: 48px;
  border-radius: var(--radius-full);
  background: linear-gradient(135deg, var(--color-primary), var(--color-secondary));
  color: #fff;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--elevation-4), var(--glow-primary);
  transition: transform var(--duration-fast) var(--ease-spring),
              box-shadow var(--duration-fast) var(--ease-standard);
}
.ai-fab:hover {
  transform: scale(1.08) translateY(-2px);
  box-shadow: var(--elevation-5), var(--glow-primary);
}
.ai-fab:active { transform: scale(0.95); }

/* Pulse ring — draws the eye without being intrusive */
.ai-fab::before {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: var(--radius-full);
  border: 2px solid var(--color-primary);
  opacity: 0;
  animation: ai-pulse 3s ease-out infinite;
}
@keyframes ai-pulse {
  0%   { transform: scale(0.9); opacity: 0.6; }
  100% { transform: scale(1.5); opacity: 0; }
}
```

**Component**: `AIAssistantButton.tsx` — renders the FAB, opens `AIAssistantDrawer` (right slide-over) with the NL query input already focused. Reuses the existing NL search infrastructure from `InventoryPage`.

---

### P8 — URL-Encoded Filter State *(Routing Enhancement)*

**What**: Persist active filters and search terms in the URL query string so views are shareable and browser-back works correctly.

**Implementation pattern** (React Router v6):
```tsx
// In InventoryPage.tsx — replace useState for filters with useSearchParams
const [searchParams, setSearchParams] = useSearchParams()

const activeFilters = useMemo(() =>
  JSON.parse(searchParams.get('filters') || '[]'),
  [searchParams]
)

const setFilters = useCallback((filters: Filter[]) => {
  setSearchParams(prev => {
    if (filters.length === 0) prev.delete('filters')
    else prev.set('filters', JSON.stringify(filters))
    return prev
  }, { replace: true })
}, [setSearchParams])

// Also encode: category, subcategory, search query, sort
```

This makes every filtered view bookmarkable and shareable — a power-user feature that Wiz does well.

---

### P9 — Connectors Catalog Enhancement *(Enhance ConnectorsPage)*

**What**: Add two UX polish items from Wiz's integration catalog: (1) left category sidebar with counts, (2) "Preview" / "Beta" badge on new connectors.

**CSS** additions:
```css
.conn-catalog-layout {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: var(--space-4);
  align-items: start;
}

.conn-cat-sidebar {
  background: var(--surface-1);
  border: 1px solid var(--border-card);
  border-radius: var(--radius-md);
  padding: var(--space-2) 0;
  position: sticky;
  top: var(--space-4);
}

.conn-cat-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px var(--space-4);
  font-size: var(--text-label-md);
  color: var(--text-secondary);
  background: none;
  border: none;
  width: 100%;
  text-align: left;
  cursor: pointer;
  border-radius: 0;
  transition: background var(--duration-micro) var(--ease-standard),
              color var(--duration-micro) var(--ease-standard);
}
.conn-cat-item:hover { background: var(--state-hover); color: var(--text-primary); }
.conn-cat-item.active { background: var(--color-primary-container); color: var(--color-primary-bright); }

.conn-cat-count {
  font-size: 10px;
  color: var(--text-disabled);
  font-variant-numeric: tabular-nums;
}

/* Preview badge */
.badge-preview {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: var(--radius-full);
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  background: var(--color-medium-dim);
  border: 1px solid var(--color-medium-border);
  color: var(--color-medium);
}
```

---

## Quick-Reference Priority Table

| Priority | Gap | Component/File | Estimated Effort |
|----------|-----|---------------|-----------------|
| **P1** | Overview Dashboard | `OverviewPage.tsx` (new) + `MetricCard.tsx` (new) | Large |
| **P2** | Trend badges on all metrics | `TrendBadge.tsx` / `TrendBadge.css` (enhance) | Small |
| **P3** | Nav flyout secondary panels | `Sidebar.tsx` + `SidebarFlyout.tsx` (new) | Medium |
| **P4** | Active filter pills in toolbar | `InventoryPage.tsx` + `FilterPill.tsx` (new) | Small |
| **P5** | Graph node semantic colors + legend | `GraphCanvas.tsx` + `tokens.css` | Medium |
| **P6** | Tabbed InspectionPane | `InspectionPane.tsx` + `inspection.css` | Medium |
| **P7** | AI assistant FAB | `AIAssistantButton.tsx` (new) | Small |
| **P8** | URL-encoded filter state | `InventoryPage.tsx` routing | Small |
| **P9** | Connector catalog category sidebar + Preview badge | `ConnectorsPage.tsx` + CSS | Small |

---

## Notes on Staying Differentiated from Wiz

dgraph.ai should **not** clone Wiz's light theme — the dark black-violet aesthetic is a genuine differentiator and brand identity signal. The improvements above operate within the existing dark system.

Similarly, Wiz's CHML colors (gray for Low) are generic. dgraph.ai's **teal for Low severity** is distinctive and should be preserved.

The primary opportunity is **information architecture density and discoverability** — Wiz's flyout navigation and dashboard-first approach make it dramatically easier to understand posture at a glance. That's the biggest UX gap to close.
