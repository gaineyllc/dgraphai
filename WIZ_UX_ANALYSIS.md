# Wiz vs dgraph.ai — UX Analysis & Gap Report
_Generated from 15 Wiz screenshot photos, April 2026_

---

## Key Finding: Wiz is a LIGHT theme platform

This is the most important insight. **Wiz uses a light/white theme** for its main content areas (avg brightness 140-195/255). dgraph.ai is built dark-first. This doesn't mean dgraph.ai needs to switch — but it means we can't directly compare most visual patterns. We need to excel at *dark mode done right*, not copy Wiz's light aesthetic.

---

## Wiz Design System — Extracted Values

### Color Palette
| Token | Value | Usage |
|---|---|---|
| Sidebar background | `#2f-34` range (~`#31343a`) | Near-black, not pure black — has slight warmth |
| Content background | `#f5f5f5` – `#ffffff` | Off-white cards, white panels |
| Top bar | `#31323a` (dark) or white (varies per page) | Inconsistent — sometimes dark, sometimes light |
| Card background | `#ffffff` + `1px solid #e5e7eb` | White cards, light gray border |
| Text primary | `#111827` | Near-black, high contrast |
| Text secondary | `#6b7280` | Medium gray |
| Text tertiary | `#9ca3af` | Light gray labels |
| Severity Critical | `#dc2626` / `#ef4444` | Red circle badge |
| Severity High | `#f97316` / `#ea580c` | Orange circle badge |
| Severity Medium | `#f59e0b` / `#d97706` | Amber circle badge |
| Severity Low | `#6b7280` | Gray circle badge |
| Positive trend | `#16a34a` + light green bg | Green + down arrow |
| Negative trend | `#dc2626` + light red bg | Red + up arrow |
| Blue accent | `#2563eb` / `#3b82f6` | Links, active states, Wiz blue |
| Progress/adoption | Wiz blue filled bar | Top nav adoption meter |

### Typography
- **Font:** Inter or similar geometric sans-serif — clean, high legibility
- **Hierarchy:**
  - Page title: 20-24px, bold (`font-weight: 700`)
  - Section headers: 14-16px, semibold
  - ALL CAPS labels: 11px, tracking wide (`letter-spacing: 0.08em`), gray
  - Metric numbers: 28-36px, extrabold (`font-weight: 800`) — very prominent
  - Body/row text: 13-14px, regular
  - Small labels: 11-12px, medium gray
- **Key pattern:** Large numbers are the star — 28-36px bold for all key metrics

### Sidebar Design
- Width: ~56px icon-only rail + flyout submenu
- Sidebar background: `#1e2124` to `#31343a` (very dark, slight blue-gray tint)
- Icon rail: thin-line icons, white/gray, 18-20px
- Active item: colored accent background pill
- Flyout: white panel with item hierarchy, section labels in ALL CAPS
- Bottom items (Lens, Connectors) separated by divider
- **No labels in collapsed state — icon only with tooltip**

### Card Design
- Background: pure white `#ffffff`
- Border: `1px solid #e5e7eb` (very subtle light gray)
- Border radius: 8px
- Padding: 16-20px
- Shadow: `0 1px 3px rgba(0,0,0,0.08)` (extremely subtle)
- No gradient, no heavy shadows — flat with just a thin border

### Severity Badge System (THE most important visual pattern)
- Shape: **Filled circle, ~20px diameter**
- Single uppercase letter: C / H / M / L
- Critical: red filled circle, white letter
- High: orange filled circle, white letter
- Medium: amber filled circle, white letter
- Low: gray filled circle, white letter
- Used everywhere consistently — tables, cards, nav, detail views

### Trend Indicators
- Pill badges with arrow + percentage
- Positive (decreasing issues): `↓ 93%` — green text, light green bg `#dcfce7`
- Negative (increasing): `↑ 10%` — red text, light red bg `#fee2e2`
- Arrow icon + bold percentage inside rounded pill

### Table Design
- Row height: ~44-48px
- Alternating white / very subtle stripe (barely visible)
- Hover: light blue/gray background
- Column headers: 11px ALL CAPS, `#6b7280`, `letter-spacing: 0.06em`
- Cell text: 13-14px, `#374151`
- Left-aligned text, right-aligned numbers
- Sort icons: small arrows on hover
- Checkbox column for multi-select
- Sticky header on scroll

### Filter Bar Pattern
- Horizontal pill filters: `All | Critical | High | Medium | Low`
- Active filter: filled blue pill, white text
- Inactive: border-only pill, gray text
- Filter bar above the table, full width
- Additional: dropdown filters for type, status, date range
- **Search integrated inline** with filter pills, not separate

### Navigation Structure (from sidebar analysis)
```
Wiz Sidebar Nav:
  Boards (sub: Platform Overview, All Boards, Champion Center, Threat Intel Center)
  Issues (sub: Risk Issues, Graph Control, Cloud Config, Service Issues, Posture Issues...)
  Threats
  Findings
  Inventory
  Explorer (Security Graph)
  Policies
  Reports
  Settings
  ─────
  Lens
  Connect(ors)
```

### Page Header Pattern
- Page title: large bold text, left aligned
- Star icon for favoriting (☆)
- Tag/badge: "Preview" or feature tags
- Utility icons: print, overflow, help
- **NO breadcrumb trails** — single page title
- Top bar has: Wiz logo | project selector | search | adoption bar | notifications | profile

### Graph/Security Graph (Explorer)
- White/light gray background
- Colored nodes: each resource type has a distinct color
- Node labels: white text on colored circle
- Edges: light gray lines
- Dense node clusters for resource relationships
- Panel on right: node details slide-in
- **Top toolbar:** search, zoom, layout controls, filter chips

---

## Gap Analysis: dgraph.ai vs Wiz

### What dgraph.ai does BETTER
1. **True dark theme** — Wiz has no dark mode; dgraph.ai's `#0a0a0f` base is cleaner
2. **Richer graph visualization** — Cytoscape with filters, infinite zoom
3. **Data Inventory taxonomy** — Wiz has no equivalent browse-by-format feature
4. **NL search** — Wiz has keyword search, dgraph.ai has natural language

### What Wiz does BETTER (gaps to close)

#### 🔴 Critical Gaps

**1. Severity badge system is missing from dgraph.ai**
- Wiz has a universal C/H/M/L badge system everywhere
- dgraph.ai has no consistent severity visual language
- Fix: Add `<SeverityBadge level="critical|high|medium|low" />` component

**2. Metric numbers are too small**
- Wiz uses 28-36px bold numbers for key metrics (142 Critical, 10 Threats)
- dgraph.ai uses ~18-20px numbers on most cards
- Fix: Increase key metric numbers to 28-32px with `font-weight: 800`

**3. Trend indicators missing**
- Wiz shows `↓ 93%` green pill / `↑ 10%` red pill for every metric
- dgraph.ai shows no delta/trend indicators
- Fix: Add `<TrendBadge pct={-93} />` component for security metrics

**4. Filter bar pattern inconsistent**
- Wiz has a universal horizontal pill filter bar on every list page
- dgraph.ai has sidebar filters (QueryWorkspace) and inline filters (Inventory) — inconsistent
- Fix: Standardize to top pill filter bar + optional sidebar for complex pages

**5. Table column headers wrong style**
- Wiz: 11px ALL CAPS, wide letter-spacing, `#6b7280`
- dgraph.ai: 10-11px uppercase — close but needs exact Wiz treatment

**6. Card borders too prominent**
- Wiz: `1px solid #e5e7eb` ultra-subtle border (on light) or `1px solid #1a1a28` (on dark)
- dgraph.ai: `1px solid #1a1a28` — correct for dark, but some cards use `#252535` which is too visible

#### 🟡 Important Gaps

**7. Page headers lack utility icons**
- Wiz has: ☆ favorite, print, share, overflow menu `⋮` on every page
- dgraph.ai: nothing in page headers

**8. Empty states underdeveloped**
- Wiz: illustrated empty states with clear CTAs and next steps
- dgraph.ai: most pages show raw blank content with no guidance

**9. Sidebar flyout submenu**
- Wiz: icon rail + flyout submenu with hierarchy
- dgraph.ai: icon rail with tooltips only — no submenu grouping

**10. Adoption/progress metric in top nav**
- Wiz: shows "Wiz Adoption" progress bar prominently
- dgraph.ai: no equivalent onboarding progress in top nav

**11. "All Caps" section labels**
- Wiz uses ALL CAPS + wide tracking for section dividers consistently
- dgraph.ai uses them in some places, missing in others

**12. Multi-column security overview cards**
- Wiz homepage: 3-column layout showing Threats | Risk Issues | Posture Issues
- dgraph.ai Security page: single-column list panels
- Fix: 3-column summary cards at top of Security page

---

## Priority Implementation List

### P0 — This week (visual parity on security pages)

```tsx
// 1. SeverityBadge component
<SeverityBadge level="critical" count={142} />
// Renders: red filled circle "C" + bold number

// 2. TrendBadge component  
<TrendBadge direction="down" pct={93} />
// Renders: ↓93% in green pill

// 3. MetricCard component
<MetricCard
  icon={ShieldAlert}
  title="Critical Issues"
  value={142}
  trend={{ direction: 'down', pct: 3 }}
  severity="critical"
/>
```

### P1 — Next sprint (layout consistency)

4. **Standardize table headers** → 11px ALL CAPS `letter-spacing: 0.06em` `color: #55557a`
5. **Add page-level utility bar** → star, share, overflow on page headers
6. **Top-of-page filter pills** → horizontal pill filter bar on Security, Connectors, Audit pages
7. **Security page 3-column summary** → Threats | Findings | CVEs side by side

### P2 — Following sprint (polish)

8. **Empty state illustrations** → each page needs a "no data" state with CTA
9. **Sidebar flyout groups** → group nav items into flyout sections
10. **Onboarding progress in header** → "4/7 setup steps complete" progress bar
11. **Increase metric font sizes** → 28-32px for hero numbers

---

## dgraph.ai Specific CSS Changes

```css
/* Fix 1: Severity badges — add these classes */
.severity-badge {
  width: 20px; height: 20px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 800; color: #fff;
  flex-shrink: 0;
}
.severity-critical { background: #dc2626; }
.severity-high     { background: #f97316; }
.severity-medium   { background: #f59e0b; }
.severity-low      { background: #6b7280; }

/* Fix 2: Trend badges */
.trend-badge {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 2px 8px; border-radius: 20px;
  font-size: 11px; font-weight: 700;
}
.trend-positive { background: #dcfce7; color: #16a34a; }
.trend-negative { background: #fee2e2; color: #dc2626; }

/* Fix 3: Hero metric numbers */
.metric-hero-number {
  font-size: 32px; font-weight: 800; line-height: 1;
  font-variant-numeric: tabular-nums; letter-spacing: -0.02em;
}

/* Fix 4: Table headers */
.table-header-cell {
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.06em; color: #55557a; /* Wiz: #6b7280 */
}

/* Fix 5: Card borders — dgraph.ai dark version of Wiz style */
.card-standard {
  background: #0e0e16; /* slightly lighter than page bg */
  border: 1px solid #1a1a28; /* ultra-subtle */
  border-radius: 10px;
}
/* Avoid: #252535 which is too visible — use #1a1a28 */
```

---

## Summary Verdict

dgraph.ai's dark theme is actually more visually distinctive than Wiz's light theme for security professionals (many work in dark environments). The gaps are not about switching themes but about:

1. **Severity language** — Wiz's C/H/M/L badge system is industry-standard; we're missing it
2. **Metric prominence** — numbers need to be bigger and bolder
3. **Trend indicators** — users need to see direction, not just current value
4. **Consistency** — filter patterns, table headers, section labels need standardization
5. **Empty states** — every page needs guidance when there's no data

Implementing the P0 and P1 items above would make dgraph.ai match or exceed Wiz's UX polish on the pages that matter most for security workflows.
