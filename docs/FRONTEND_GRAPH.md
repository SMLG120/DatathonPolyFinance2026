# Exposure network update

Requested by the owner: use https://github.com/vasturiano/3d-force-graph.
This replaces the earlier plain-ThreeJS column renderer specified in PLAN P9.

- Lazy-loaded browser-only `3d-force-graph`, with fixed node positions for a stable before/after comparison and orbit navigation.
- Portfolio -> direct holding or fund -> selected issuer. The figures come from the existing checked API model.
- Unattributed holdings are an amber branch with an upper-bound label, never a proven connection to an issuer.
- Node size, link width, position and distance encode no financial amount.
- The numeric table, source-selection buttons and evidence drawer remain available.
- Users can switch to the simple chart. Narrow screens, reduced motion, forced colours and unavailable WebGL retain the existing fallback.
- No changes to API contracts or financial calculations.
- New introduction explains the workflow; a progress strip indicates the current stage.

Local verification: explorer/model/capability/integration tests, TypeScript and ESLint.
Production export can be checked with `npm run build -- --webpack` when this environment's Turbopack process/port restrictions prevent the default build.
