"""Independent re-derivation of the engine fixtures' expected numbers. Test helper only.

This is NOT the product engine (that lives in backend/engine and is written by
another owner). It is a second, deliberately plain derivation used to re-check
the numbers typed into contracts/fixtures/engine from HAND_CALCS.md, plus a
brute-force scan used to confirm every max_compliant boundary. Plain loops, no
closed-form boundary algebra, so an algebra slip in the hand calculation cannot
hide here.
"""

from __future__ import annotations

from datetime import date

EPS = 1e-9
SCENARIO = {"replay_2022": ("2021-12-31", "2022-12-30")}
MAX_AGE_DAYS = 7  # a price or FX rate older than this at the base or end date is not usable


def _status_max(lower, upper, limit):
    if upper <= limit + EPS:
        return "PASS"
    return "FAIL" if lower > limit + EPS else "UNKNOWN"


def _status_min(lower, upper, limit):
    if lower >= limit - EPS:
        return "PASS"
    return "FAIL" if upper < limit - EPS else "UNKNOWN"


def look_through(positions, universe):
    """positions: {instrument_id: weight}. Returns per-issuer known exposure pieces and the unknown parts."""
    instruments = universe["instruments"]["instruments"]
    funds = universe["holdings"]["funds"]
    direct, via, out_of_scope, coverage = {}, {}, [], []
    uncovered = 0.0
    for instrument_id, weight in positions.items():
        meta = instruments[instrument_id]
        if not meta["equity_scope"]:
            out_of_scope.append((instrument_id, weight))
            continue
        if not meta["is_fund"]:
            direct[meta["issuer_id"]] = direct.get(meta["issuer_id"], 0.0) + weight
            continue
        fund = funds.get(instrument_id)
        if fund is None:
            uncovered += weight
            coverage.append((instrument_id, weight, 0.0, 0.0, weight, "MISSING"))
            continue
        c = fund["coverage_fraction"]
        labelled = sum(r["weight_fraction"] for r in fund["holdings"] if r["sector"] is not None)
        gap = weight * max(0.0, 1.0 - c)
        uncovered += gap
        coverage.append((instrument_id, weight, c, labelled, gap, "COVERED" if c >= 1 - EPS else "PARTIAL"))
        for row in fund["holdings"]:
            key = (row["issuer_id"], instrument_id)
            via[key] = via.get(key, 0.0) + weight * row["weight_fraction"]
    lower = dict(direct)
    for (issuer_id, _fund), known in via.items():
        lower[issuer_id] = lower.get(issuer_id, 0.0) + known
    return {"direct": direct, "via": via, "lower": lower, "uncovered": uncovered, "out_of_scope": out_of_scope, "coverage": coverage}


def _causes(lt, extra_unclassified=0.0, registry=False):
    causes = set()
    for (_fund, _w, _c, _lab, gap, status) in lt["coverage"]:
        if status == "PARTIAL" and gap > EPS:
            causes.add("PARTIAL_HOLDINGS")
        if status == "MISSING" and gap > EPS:
            causes.add("MISSING_HOLDINGS")
    if extra_unclassified > EPS:
        causes.add("UNCLASSIFIED_SECTOR")
    if registry:
        causes.add("REGISTRY_ABSENCE")
    return causes


def replay(weights, universe, scenario_id, required=()):
    """weights: {instrument_id: weight}; cash is the remainder and earns 0.

    ``required`` lists further instruments that must also have usable history (the instruments of the PROPOSED
    portfolio when the STARTING one is replayed): one check uses one replay universe. When any instrument lacks a
    price (or FX rate) on or before the base or end date, or the latest one is more than MAX_AGE_DAYS old, the
    result carries ``missing`` and no measures.
    """
    base_date, end_date = SCENARIO[scenario_id]
    prices = universe["market_data"]["prices"]
    fx = universe["market_data"]["fx_usdcad"]

    def latest(series, day):
        found = None
        for d, v in series:
            if d <= day:
                found = (d, v)
        return found

    def age(day, observed):
        return (date.fromisoformat(day) - date.fromisoformat(observed)).days

    def value_cad(instrument_id, day):
        entry = prices.get(instrument_id)
        if entry is None:
            return None
        price = latest(entry["series"], day)
        if price is None:
            return None
        if entry["currency"] == "CAD":
            return price[1], price[0], None
        rate = latest(fx, day)
        if rate is None:
            return None
        return price[1] * rate[1], price[0], rate[0]

    def usable(instrument_id, day):
        found = value_cad(instrument_id, day)
        if found is None or age(day, found[1]) > MAX_AGE_DAYS:
            return None
        if found[2] is not None and age(day, found[2]) > MAX_AGE_DAYS:
            return None
        return found

    base, end, rows, missing = {}, {}, [], []
    for instrument_id in list(weights) + [i for i in required if i not in weights]:
        b0, e0 = usable(instrument_id, base_date), usable(instrument_id, end_date)
        if b0 is None or e0 is None:
            missing.append(instrument_id)
            continue
        base[instrument_id], end[instrument_id] = b0, e0
        usd = prices[instrument_id]["currency"] == "USD"
        rows.append({
            "instrument_id": instrument_id, "currency": prices[instrument_id]["currency"],
            "base_price_date": b0[1], "end_price_date": e0[1],
            "base_price_age_days": age(base_date, b0[1]), "end_price_age_days": age(end_date, e0[1]),
            "base_fx_date": b0[2] if usd else None, "end_fx_date": e0[2] if usd else None,
            "base_fx_age_days": age(base_date, b0[2]) if usd else None, "end_fx_age_days": age(end_date, e0[2]) if usd else None,
            "return_cad": e0[0] / b0[0] - 1.0,
        })
    if missing:
        return {"missing": missing, "rows": rows}
    cash = 1.0 - sum(weights.values())
    days = sorted({d for i in weights for d, _ in prices[i]["series"] if base_date < d <= end_date})
    peak, worst, worst_day, value = 1.0, 0.0, None, 1.0
    for day in days:
        value = cash + sum(w * value_cad(i, day)[0] / base[i][0] for i, w in weights.items())
        peak = max(peak, value)
        drawdown = value / peak - 1.0
        if drawdown < worst - EPS:
            worst, worst_day = drawdown, day
    terminal = cash + sum(w * end[i][0] / base[i][0] for i, w in weights.items()) - 1.0
    return {"terminal": terminal, "drawdown": worst, "drawdown_date": worst_day, "rows": rows, "missing": []}


def evaluate_rule(rule, positions, universe, required=()):
    """Return status, measured (lower, upper) or None, breaching issuers and causes for one rule on one portfolio."""
    kind, params, limit = rule["rule_type"], rule["parameters"], rule["threshold"]
    if kind == "scenario_loss_budget":
        result = replay(positions, universe, params["scenario_id"], required)
        if result["missing"]:
            return {"status": "UNKNOWN", "measured": None, "breaching": [], "causes": {"INSUFFICIENT_HISTORY"}, "replay": result}
        loss = -result["terminal"]
        return {"status": _status_max(loss, loss, limit), "measured": (loss, loss), "breaching": [], "causes": set(), "replay": result}

    lt = look_through(positions, universe)
    instruments = universe["instruments"]["instruments"]
    funds = universe["holdings"]["funds"]
    extra = lt["uncovered"]
    bounds = lambda issuer: (lt["lower"].get(issuer, 0.0), lt["lower"].get(issuer, 0.0) + extra)  # noqa: E731

    if kind == "max_issuer_exposure":
        scope = params["issuer_scope"]
        issuers = list(lt["lower"]) if scope == "any" else [scope]
        lower = max([lt["lower"].get(i, 0.0) for i in issuers], default=0.0)
        upper = lower + extra
        status = _status_max(lower, upper, limit)
        breaching = sorted(((i,) + bounds(i) for i in issuers if lt["lower"].get(i, 0.0) > limit + EPS), key=lambda t: (-t[1], t[0]))
        return {"status": status, "measured": (lower, upper), "breaching": breaching if status == "FAIL" else [], "causes": _causes(lt), "lt": lt}
    if kind == "min_issuer_exposure":
        lower, upper = bounds(params["issuer_id"])
        return {"status": _status_min(lower, upper, limit), "measured": (lower, upper), "breaching": [], "causes": _causes(lt), "lt": lt}
    if kind == "exclusion" and params["definition"]["kind"] == "named_issuers":
        members = params["definition"]["issuer_ids"]
        lower = sum(lt["lower"].get(i, 0.0) for i in members)
        upper = lower + extra
        status = _status_max(lower, upper, limit)
        breaching = sorted(((i,) + bounds(i) for i in members if lt["lower"].get(i, 0.0) > EPS), key=lambda t: (-t[1], t[0]))
        return {"status": status, "measured": (lower, upper), "breaching": breaching if status == "FAIL" else [], "causes": _causes(lt), "lt": lt}
    if kind == "exclusion":
        sector = params["definition"]["sector"]
        known, unclassified = {}, 0.0
        for instrument_id, weight in positions.items():
            meta = instruments[instrument_id]
            if not meta["equity_scope"]:
                continue
            if not meta["is_fund"]:
                if meta["sector"] is None:
                    unclassified += weight
                elif meta["sector"] == sector:
                    known[meta["issuer_id"]] = known.get(meta["issuer_id"], 0.0) + weight
                continue
            fund = funds.get(instrument_id)
            for row in (fund["holdings"] if fund else []):
                if row["sector"] is None:
                    unclassified += weight * row["weight_fraction"]
                elif row["sector"] == sector:
                    known[row["issuer_id"]] = known.get(row["issuer_id"], 0.0) + weight * row["weight_fraction"]
        lower = sum(known.values())
        upper = lower + extra + unclassified
        status = _status_max(lower, upper, limit)
        breaching = sorted(((i,) + bounds(i) for i, v in known.items() if v > EPS), key=lambda t: (-t[1], t[0]))
        return {"status": status, "measured": (lower, upper), "breaching": breaching if status == "FAIL" else [],
                "causes": _causes(lt, extra_unclassified=unclassified), "lt": lt}
    if kind == "controversy_exclusion":
        criteria = params["criteria"]
        flagged = {
            r["issuer_id"] for r in universe["controversies"]["records"]
            if r["nature"] in criteria["natures"] and (criteria["event_date_from"] is None or r["event_date"] >= criteria["event_date_from"])
        }
        lower = sum(v for i, v in lt["lower"].items() if i in flagged)
        upper = sum(w for i, w in positions.items() if instruments[i]["equity_scope"])
        status = _status_max(lower, upper, limit)
        breaching = sorted(((i,) + bounds(i) for i in flagged if lt["lower"].get(i, 0.0) > EPS), key=lambda t: (-t[1], t[0]))
        return {"status": status, "measured": (lower, upper), "breaching": breaching if status == "FAIL" else [],
                "causes": _causes(lt, registry=upper - lower > EPS), "lt": lt}
    raise ValueError(kind)


def with_target(portfolio, instrument_id, target):
    positions = {p["instrument_id"]: p["weight"] for p in portfolio["positions"]}
    start = positions.get(instrument_id, 0.0)
    positions[instrument_id] = target
    if positions[instrument_id] == 0.0:
        del positions[instrument_id]
    return positions, start, portfolio["cash_weight"] - (target - start)


def evaluated_rules(policy):
    return [r for r in policy["rules"] if r["status"] == "CONFIRMED" and r["threshold"] is not None]


def all_pass_and_funded(case, universe, target):
    portfolio, policy, request = case["inputs"]["portfolio"], case["inputs"]["policy"], case["inputs"]["purchase_request"]
    positions, _start, cash_after = with_target(portfolio, request["instrument_id"], target)
    statuses = [evaluate_rule(r, positions, universe)["status"] for r in evaluated_rules(policy)]
    return cash_after >= -EPS and all(s == "PASS" for s in statuses), cash_after >= -EPS and "FAIL" not in statuses


def scan_boundary(case, universe, steps=4000):
    """Brute force over target weights in (w0, w0 + cash]. Returns (largest all-PASS target or None, any target without a proven FAIL)."""
    portfolio, request = case["inputs"]["portfolio"], case["inputs"]["purchase_request"]
    start = {p["instrument_id"]: p["weight"] for p in portfolio["positions"]}.get(request["instrument_id"], 0.0)
    cash = portfolio["cash_weight"]
    if cash <= EPS:
        return None, False, 0.0  # no cash: there is no target above the starting weight to try
    best, some_not_fail = None, False
    for k in range(1, steps + 1):
        target = start + cash * k / steps
        passed, not_failed = all_pass_and_funded(case, universe, target)
        if passed:
            best = target
        some_not_fail = some_not_fail or not_failed
    return best, some_not_fail, cash / steps
