## UI component rules — pre-Stage II foundation

These rules are binding for every Program screen added in Stage II (SEO, CRM, Ads, CMS) and beyond.

### Stat discipline

- Every portfolio-level or screen-level KPI number uses `<Stat>` from `components/ui/Stat.tsx`.
- Never hand-roll a `<div className="metric-tile">` to render a stat — if `Stat` doesn't support a needed variant, extend `Stat`, don't create a parallel implementation.
- `<Panel>` is allowed for section containers but not for individual KPI tiles — use `Stat` inside `Panel` if needed.

### One composition per viewport

- Any screen may have at most one dominant panel above the fold (the first thing the eye lands on after the header).
- If a new Program screen wants a second competing above-the-fold panel, it goes behind `<CollapsibleSection>` by default — this is a fixed ceiling, not a per-feature judgment call.

### Progressive disclosure

- `<CollapsibleSection>` from `components/ui/CollapsibleSection.tsx` is the single implementation of "show more" for every screen.
- No screen may hand-roll its own `useState` toggle for collapsible content — use `<CollapsibleSection label="...">` instead.
- Owner workload, wins, AI value, and any future secondary analytics go behind `<CollapsibleSection>`, collapsed by default.

### Adding a stat

- Any new stat added to an existing screen must either (a) remove or consolidate an existing stat, or (b) justify in the PR description why the screen still passes "one composition per viewport" with the addition.
- This is the mechanism that prevents stat-grid sprawl as Stage II adds more Programs.

### New screen checklist

Before building any new Stage II screen (Pulse, SEO segments, CRM attribution, etc.):

1. Import `Stat` and `CollapsibleSection` from `components/ui/`
2. Render one dominant panel above the fold
3. Put everything else behind `<CollapsibleSection>`
4. Use `<Stat>` for every KPI number
5. Confirm the loading/error/empty states render correctly
