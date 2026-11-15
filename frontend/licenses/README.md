# Frontend component sources

Components are vendored and adapted, following the copy-and-paste model of both projects.

- `src/components/shadcn/button-variants.ts`: shadcn/ui button variants, MIT. Source: https://github.com/shadcn-ui/ui/blob/main/apps/v4/registry/new-york-v4/ui/button.tsx
- `src/components/tremor/Card.tsx`: Tremor Card v1.0.0, Apache-2.0. Source: https://github.com/tremorlabs/tremor/blob/main/src/components/Card/Card.tsx
- `src/components/tremor/ProgressBar.tsx`: Tremor ProgressBar v0.0.3, Apache-2.0. Source: https://github.com/tremorlabs/tremor/blob/main/src/components/ProgressBar/ProgressBar.tsx

Adaptations: existing contrast-tested palette, app button API and soft-disabled behavior, semantic section headings, finite progress bounds, reduced-motion transitions. Shared class merging uses clsx and tailwind-merge. Upstream licenses are included alongside this file. No hosted component service is needed.

Panel wraps Tremor Card; StageFrame uses Tremor ProgressBar; Button and LinkButton use the shared shadcn-derived variants. The exposure network remains 3d-force-graph, with its existing accessible chart and table fallback. Financial calculations remain unchanged.

## Visual theme

The interface uses a shadcn-inspired zinc palette (off-white canvas, white cards, charcoal actions), compact pill badges and inset segmented navigation. Data charts retain a Tremor-inspired blue scale; green/red/amber states always include words and icons. Borders, text and chart marks are checked by `npm run contrast`. Card spacing and mobile stacking remain responsive.
