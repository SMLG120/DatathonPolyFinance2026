/**
 * The single import point for fixture data.
 *
 * PHASE 1 (now): `contracts/fixtures/api/*.json` and `contracts/scenarios/*.json`
 * were not available, so this re-exports the provisional stand-in.
 *
 * PHASE 2: run `npm run sync:contracts`, import the generated JSON copies from
 * `@/generated/contracts/...` here, type them with `@/lib/contracts`, and
 * delete `./provisional-fixtures.ts`. The fixtures client
 * (`src/lib/api/fixtures-client.ts`) is the only consumer.
 */
export {
  FIXTURE_CALCULATION_VERSION,
  FIXTURE_CLOCK_START,
  FIXTURE_SCENARIOS,
  FIXTURE_SOURCES,
  FIXTURE_VALUATION_DATE,
  type FixtureRuleMeasure,
  type FixtureScenario,
  type FixtureScenarioReplay,
} from "./provisional-fixtures";
