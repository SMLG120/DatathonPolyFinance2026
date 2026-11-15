import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import type { CheckResult } from "./contract-types";
import { buildExplorerModel, type ExplorerReady } from "./model";

/**
 * The adapter is tested against the contract's own fixtures, read from
 * `contracts/fixtures/api/`. Expected numbers are taken from the fixture being
 * tested, never typed here, so the tests keep holding when fixture values change
 * and fail only if the adapter stops copying what the response says.
 */
const FIXTURES = path.resolve(import.meta.dirname, "../../../../contracts/fixtures/api");

function isCheckResult(value: unknown): value is CheckResult {
  return typeof value === "object" && value !== null && "rule_results" in value && "execution" in value && "exposure" in value;
}

/** Every CheckResult found anywhere in a fixture's response body. */
function resultsIn(value: unknown, found: CheckResult[] = []): CheckResult[] {
  if (isCheckResult(value)) found.push(value);
  if (Array.isArray(value)) value.forEach((item) => resultsIn(item, found));
  else if (typeof value === "object" && value !== null) Object.values(value).forEach((item) => resultsIn(item, found));
  return found;
}

const cases = readdirSync(FIXTURES)
  .filter((name) => name.endsWith(".json"))
  .flatMap((name) => {
    const fixture = JSON.parse(readFileSync(path.join(FIXTURES, name), "utf8")) as { response_body: unknown };
    return resultsIn(fixture.response_body).map((result, index) => ({ name: `${name}#${index}`, result }));
  });

function load(name: string): CheckResult {
  const found = cases.find((item) => item.name === `${name}#0`);
  if (!found) throw new Error(`fixture ${name} holds no check result`);
  return structuredClone(found.result);
}

function ready(result: CheckResult, issuerId?: string): ExplorerReady {
  const model = buildExplorerModel(result, { dataOrigin: "FIXTURE", issuerId });
  if (model.status !== "READY") throw new Error(`expected READY, got ${model.reason}`);
  return model;
}

describe("buildExplorerModel against every contract fixture", () => {
  it("finds check results to test", () => {
    expect(cases.length).toBeGreaterThan(3);
  });

  it.each(cases)("$name: copies the response and invents nothing", ({ result }) => {
    const before = JSON.stringify(result);
    const first = buildExplorerModel(result, { dataOrigin: "FIXTURE" });
    expect(JSON.stringify(result), "the adapter changed its input").toBe(before);

    if (result.execution.status !== "OK" || result.exposure === null || result.exposure.issuers.length === 0) {
      expect(first.status).toBe("UNAVAILABLE");
      return;
    }

    for (const issuer of result.exposure.issuers) {
      const model = ready(result, issuer.issuer_id);
      expect(model.issuerName).toBe(issuer.name);

      for (const state of ["starting", "proposed"] as const) {
        const column = state === "starting" ? model.current : model.proposed;
        const source = issuer[state];
        const extra = result.exposure.possible_extra[state];

        expect(column.known).toBe(source.lower);
        expect(column.upper).toBe(source.upper);
        expect(column.isRange).toBe(source.upper !== source.lower);

        const direct = column.segments.filter((segment) => segment.kind === "DIRECT");
        expect(direct).toHaveLength(1);
        expect(direct[0]?.value).toBe(source.direct);

        const funds = column.segments.filter((segment) => segment.kind === "FUND");
        expect(funds.map((segment) => [segment.fundId, segment.value])).toEqual(source.indirect_by_fund.map((item) => [item.fund_id, item.known]));

        // Unresolved weight is drawn exactly when the API reports one, with the API's number.
        const unresolved = column.segments.filter((segment) => segment.kind === "UNRESOLVED");
        expect(unresolved).toHaveLength(extra > 0 ? 1 : 0);
        if (extra > 0) expect(unresolved[0]?.value).toBe(extra);

        for (const segment of column.segments) expect(segment.value).toBeLessThanOrEqual(model.axisMax);
      }
      // One scale for both columns, tall enough for everything drawn.
      expect(model.axisMax).toBeGreaterThanOrEqual(Math.max(model.current.upper, model.proposed.upper, model.limit?.value ?? 0));
      expect(new Set([...model.current.segments, ...model.proposed.segments].map((segment) => segment.id)).size).toBe(
        model.current.segments.length + model.proposed.segments.length,
      );
    }
  });
});

describe("Robert, NVDA purchase (investigation_robert_succeeded.json)", () => {
  const result = load("investigation_robert_succeeded.json");
  const model = ready(result);

  it("selects the first issuer row and carries the result's identity", () => {
    expect(model.issuerId).toBe(result.exposure!.issuers[0]?.issuer_id);
    expect(model.policyVersion).toBe(result.policy_version);
    expect(model.calculationVersion).toBe(result.calculation_version);
    expect(model.valuationDate).toBe(result.valuation_date);
    expect(model.preview).toBe(false);
    expect(model.dataOrigin).toBe("FIXTURE");
  });

  it("takes the limit from the single issuer-cap rule result, with the engine's status", () => {
    const cap = result.rule_results.find((rule) => rule.rule_type === "max_issuer_exposure")!;
    expect(model.limit).toEqual({ ruleId: cap.rule_id, value: cap.limit, ruleStatus: cap.status, isDraft: false });
    expect(model.limitUnavailableReason).toBeNull();
  });

  it("links a fund segment to its evidence record, formula and holdings date when the response has them", () => {
    const record = result.evidence.find((item) => item.metric_id === "issuer_exposure_via_fund" && item.subject.id === model.issuerId)!;
    const segment = model.proposed.segments.find((item) => item.kind === "FUND" && item.fundId === record.subject.via_fund_id)!;
    const coverage = result.data_coverage.find((row) => row.fund_id === segment.fundId)!;
    expect(segment.evidenceId).toBe(record.evidence_id);
    expect(segment.formula).toBe(record.formula);
    expect(segment.holdingsDate).toBe(coverage.holdings_date);
    expect(segment.sourceId).toBe(coverage.source_id);
  });

  it("does not borrow the PROPOSED evidence record for the STARTING column", () => {
    const hasStartingRecord = result.evidence.some(
      (item) => item.metric_id === "issuer_exposure_via_fund" && item.subject.id === model.issuerId && item.subject.portfolio_state === "STARTING",
    );
    const segment = model.current.segments.find((item) => item.kind === "FUND")!;
    expect(segment.evidenceId === null).toBe(!hasStartingRecord);
  });

  it("the measured exposure is the same after the cap is raised; only the limit differs", () => {
    const after = ready(load("investigation_robert_after_challenge_succeeded.json"));
    expect(after.proposed.known).toBe(model.proposed.known);
    expect(after.proposed.upper).toBe(model.proposed.upper);
    expect(after.proposed.segments.map((segment) => segment.value)).toEqual(model.proposed.segments.map((segment) => segment.value));
    expect(after.limit!.value).not.toBe(model.limit!.value);
    expect(after.policyVersion).not.toBe(model.policyVersion);
  });
});

describe("what the adapter refuses to make up", () => {
  it("execution not OK: unavailable, with the engine's message", () => {
    const result = load("check_invalid_request.json");
    const model = buildExplorerModel(result, { dataOrigin: "LIVE" });
    expect(model).toEqual({ status: "UNAVAILABLE", reason: "EXECUTION_NOT_OK", message: result.execution.message, dataOrigin: "LIVE" });
  });

  it("an issuer the response does not list: unavailable, not an empty chart", () => {
    const model = buildExplorerModel(load("investigation_robert_succeeded.json"), { dataOrigin: "FIXTURE", issuerId: "NOT_IN_RESULT" });
    expect(model.status).toBe("UNAVAILABLE");
  });

  it("no exposure section, or no rows: unavailable", () => {
    const none = load("investigation_robert_succeeded.json");
    none.exposure = null;
    expect(buildExplorerModel(none, { dataOrigin: "FIXTURE" })).toMatchObject({ status: "UNAVAILABLE", reason: "NO_EXPOSURE_SECTION" });
    const empty = load("investigation_robert_succeeded.json");
    empty.exposure!.issuers = [];
    expect(buildExplorerModel(empty, { dataOrigin: "FIXTURE" })).toMatchObject({ status: "UNAVAILABLE", reason: "NO_ISSUER_ROWS" });
  });

  it("a fund without a coverage row or evidence record: nulls, not guesses", () => {
    const result = load("investigation_robert_succeeded.json");
    result.data_coverage = [];
    result.evidence = [];
    const segment = ready(result).proposed.segments.find((item) => item.kind === "FUND")!;
    expect(segment).toMatchObject({ holdingsDate: null, sourceId: null, coverageStatus: null, evidenceId: null, formula: null });
  });

  it("no issuer-cap rule, or several: no limit line, with the reason", () => {
    const none = load("investigation_robert_succeeded.json");
    none.rule_results = none.rule_results.filter((rule) => rule.rule_type !== "max_issuer_exposure");
    expect(ready(none)).toMatchObject({ limit: null, limitUnavailableReason: "NO_ISSUER_CAP_RULE" });

    const several = load("investigation_robert_succeeded.json");
    const cap = several.rule_results.find((rule) => rule.rule_type === "max_issuer_exposure")!;
    several.rule_results.push({ ...cap, rule_id: "second-cap", limit: 0.2 });
    expect(ready(several)).toMatchObject({ limit: null, limitUnavailableReason: "SEVERAL_ISSUER_CAP_RULES" });
  });

  it("a preview marks the limit as a draft", () => {
    const preview = load("check_robert_preview.json");
    expect(preview.preview).toBe(true);
    const model = buildExplorerModel(preview, { dataOrigin: "FIXTURE" });
    if (model.status === "READY" && model.limit) expect(model.limit.isDraft).toBe(true);
    else expect(model.status === "UNAVAILABLE" || model.limit === null).toBe(true);
  });

  it("uncovered fund weight is a labelled segment with the API's value, never zero and never folded into the known total", () => {
    const result = load("investigation_robert_succeeded.json");
    const extra = result.exposure!.possible_extra.proposed;
    expect(extra, "this fixture is expected to have partial coverage").toBeGreaterThan(0);
    const model = ready(result);
    const unresolved = model.proposed.segments.find((segment) => segment.kind === "UNRESOLVED")!;
    expect(unresolved.value).toBe(extra);
    expect(model.proposed.known).toBe(result.exposure!.issuers[0]?.proposed.lower);
    expect(model.proposed.isRange).toBe(true);
    expect(model.unknownCauses).toEqual(result.rule_results.find((rule) => rule.rule_type === "max_issuer_exposure")!.unknown_causes);
  });
});
