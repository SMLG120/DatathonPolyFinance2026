/**
 * The single import point for shared API types.
 *
 * Components, hooks and tests import types from `@/lib/contracts` and from
 * nowhere else, so swapping the source below is the whole type migration.
 *
 * PHASE 1 (now): `contracts/typescript/contracts.ts` was not available, so this
 * re-exports the provisional guess in `./provisional-types`.
 *
 * PHASE 2: run `npm run sync:contracts`, then replace the line below with
 *   export * from "@/generated/contracts/contracts";
 * and delete `./provisional-types.ts`.
 */
export * from "./provisional-types";
