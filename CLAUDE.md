# Before You Buy — repository instructions

Datathon prototype (PolyFinances AlphaForge AI 2026). It checks whether a
proposed portfolio change respects an investor's explicitly confirmed rules
and shows evidence the investor can inspect and challenge. Fictional
simulation only: no advice, no recommendations, no trades, no forecasts.

- Binding rules: `docs/BUILD_BRIEF.md`. Frozen choices, environment and the
  file ownership map: `docs/LEAD_DECISIONS.md`. Shared schemas: `contracts/`.
- Verdicts come from the deterministic engine in `backend/engine/`, never from
  a model. Units are portfolio fractions (10% = 0.10).
- Deployed code is Python standard library plus `boto3` only.
- AWS: account `010928212265`, region `us-east-1` only. Use the AWS MCP tool,
  not the AWS CLI. The account is deleted after 2026-11-16.
- Never commit credentials, `.env` files, `reference/`, `data/raw/` or the
  Yahoo-derived starter prices. See `.gitignore`.
- Development agents are defined in `.claude/agents/`.
