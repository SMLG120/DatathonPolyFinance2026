/**
 * The exposure panel holds two drawings: the chart of every company the
 * engine sent, and, inside the explorer, the view of one company (flat when
 * the 3D drawing cannot be used, as in a test DOM). Tests name the one they
 * mean.
 */

/** The chart of every company: the one placed directly in the exposure panel. */
export function overviewChart(scope: ParentNode = document): HTMLElement {
  const chart = scope.querySelector<HTMLElement>('[data-testid="exposure-views"] > [data-testid="exposure-chart"]');
  if (!chart) throw new Error("The exposure panel shows no chart of every company.");
  return chart;
}

/** The explorer's flat view of one company, shown where the 3D drawing would be. */
export function explorerFlatChart(scope: ParentNode = document): HTMLElement {
  const chart = scope.querySelector<HTMLElement>('[data-testid="exposure-explorer"] [data-testid="explorer-fallback"] [data-testid="exposure-chart"]');
  if (!chart) throw new Error("The explorer shows no flat chart.");
  return chart;
}
