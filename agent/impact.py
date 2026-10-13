"""Business-impact model. Every input is an assumption the user can change.

Cost basis (per month):
  by hand      = requests x hours x hourly cost
  agent        = model call + human review + rework of wrong decisions   (varies with volume)
               + run-and-maintain team + build cost spread over a period  (fixed)
"""
import pandas as pd

DEFAULTS = {
    "requests_per_month": 10_000,   # correction requests the company receives each month
    "manual_hours": 2.0,            # staff hours to resolve one request by hand (Ramp: "hours")
    "hourly_cost": 600.0,           # fully loaded cost of one staff hour, INR (about Rs 1 lakh a month at 165 h)
    "ai_cost": 2.0,                 # model call + retrieval per request, INR
    "review_share": 0.10,           # share of requests a person still reviews
    "review_hours": 0.5,            # hours of review per reviewed request
    "rework_share": 0.08,           # share of agent decisions that are wrong and get redone by hand
    "current_coverage": 0.015,      # share of requests staff can handle today (1.5% in 2024, per the Ramp write-up)
    "fte_hours": 165.0,             # working hours per person per month
    "build_cost": 3_600_000.0,      # one-time build and integration, INR
    "run_cost": 400_000.0,          # monthly cost of the team and tools that monitor and maintain the agent, INR
    "rules_run_cost": 100_000.0,    # monthly cost of keeping a rules-only matcher running and its rules updated, INR
    "amortise_months": 24.0,        # months over which the build cost is spread
}


def compute(p: dict) -> dict:
    n = p["requests_per_month"]
    manual_req = p["manual_hours"] * p["hourly_cost"]
    review_req = p["review_share"] * p["review_hours"] * p["hourly_cost"]
    rework_req = p["rework_share"] * manual_req
    ai_req = p["ai_cost"] + review_req + rework_req                      # marginal cost per request
    build_month = p["build_cost"] / p["amortise_months"] if p["amortise_months"] else 0.0
    fixed_month = p["run_cost"] + build_month
    fixed_req = fixed_month / n if n else 0.0
    allin_req = ai_req + fixed_req                                        # fully loaded cost per request

    manual_total = n * manual_req
    ai_total = n * ai_req                                                 # variable part
    programme_total = ai_total + fixed_month                              # everything the agent costs per month
    hours_manual = n * p["manual_hours"]
    hours_ai = n * (p["review_share"] * p["review_hours"] + p["rework_share"] * p["manual_hours"])
    handled_today = n * p["current_coverage"]
    spend_today = handled_today * manual_req
    unserved = n - handled_today
    extra_vs_today = programme_total - spend_today

    saving_per_req = manual_req - ai_req                                  # what each request saves before fixed costs
    return {
        "manual_req": manual_req, "ai_req": ai_req, "allin_req": allin_req, "fixed_req": fixed_req,
        "ai_parts": {"Model + retrieval": p["ai_cost"], "Human review": review_req,
                     "Rework of wrong decisions": rework_req, "Run + maintain team": p["run_cost"] / n if n else 0.0,
                     "Build (spread over period)": build_month / n if n else 0.0},
        "reduction": 1 - allin_req / manual_req if manual_req else 0,          # all-in
        "reduction_marginal": 1 - ai_req / manual_req if manual_req else 0,
        "manual_total": manual_total, "ai_total": ai_total, "fixed_month": fixed_month, "build_month": build_month,
        "programme_total": programme_total,
        "gross_benefit": manual_total,                                        # cost of answering everything by hand
        "net_vs_hand": manual_total - programme_total,
        "hours_manual": hours_manual, "hours_ai": hours_ai, "hours_today": handled_today * p["manual_hours"],
        "fte_manual": hours_manual / p["fte_hours"], "fte_ai": hours_ai / p["fte_hours"],
        "fte_today": handled_today * p["manual_hours"] / p["fte_hours"],
        "handled_today": handled_today, "unserved_today": unserved,
        "spend_today": spend_today, "extra_vs_today": extra_vs_today,
        "coverage_multiple": n / handled_today if handled_today else 0,
        "spend_multiple": programme_total / spend_today if spend_today else 0,
        # break-evens
        "break_even_rework": (manual_req - p["ai_cost"] - review_req - fixed_req) / manual_req if manual_req else 0,
        "break_even_volume": fixed_month / saving_per_req if saving_per_req > 0 else float("inf"),
        "value_threshold": extra_vs_today / unserved if unserved else 0,       # worth per extra request answered
        # rules + people: rules take the easy share at no extra cost, people do the rest by hand (generous to the rules)
        "break_even_hard_share": max(0.0, (programme_total - p["rules_run_cost"]) / manual_total) if manual_total else 0,
        # hybrid: rules take the easy share, the agent takes the hard share. The fixed run and build cost still applies.
        # It beats 'rules + people' once the hard share is above this (assumes the easy share is routed perfectly).
        "break_even_hybrid_share": max(0.0, fixed_month / (manual_total - ai_total)) if manual_total > ai_total else 0,
    }


def sensitivity(p: dict, review_shares=(0.05, 0.10, 0.20, 0.30), rework_shares=(0.04, 0.08, 0.12, 0.20)) -> pd.DataFrame:
    rows = {}
    for rv in review_shares:
        rows[f"{int(rv * 100)}% reviewed"] = {
            f"{int(rw * 100)}% rework": compute({**p, "review_share": rv, "rework_share": rw})["reduction"]
            for rw in rework_shares}
    return pd.DataFrame(rows).T


def vs_rules(p: dict, shares=(0.05, 0.10, 0.15, 0.20, 0.30, 0.50)) -> pd.DataFrame:
    """Monthly cost of three set-ups, for several shares of hard requests: rules for the easy requests and people for the rest,
    the agent for everything, and the hybrid (rules for the easy requests, the agent for the hard ones).

    Generous to the rules and the hybrid: they answer every easy request correctly, cost only their run cost, and never misroute a hard request."""
    r = compute(p)
    rows = []
    for h in shares:
        rules_people = p["rules_run_cost"] + h * r["manual_total"]
        hybrid = p["rules_run_cost"] + h * r["ai_total"] + r["fixed_month"]
        options = {"Rules + people": rules_people, "AI agent for all": r["programme_total"], "Rules + AI agent": hybrid}
        rows.append({"Share of requests that need an AI": h, **options, "Cheapest": min(options, key=options.get)})
    return pd.DataFrame(rows)


def wilson_low(k: int, n: int, z: float = 1.96) -> float:
    """Lower end of the 95% Wilson interval for k correct out of n."""
    if n == 0:
        return 0.0
    p = k / n
    centre = p + z * z / (2 * n)
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (centre - half) / (1 + z * z / n)


def inr(x: float) -> str:
    """Indian-style money: lakh / crore for large values."""
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e7:
        return f"{sign}₹{x / 1e7:.2f} crore"
    if x >= 1e5:
        return f"{sign}₹{x / 1e5:.1f} lakh"
    return f"{sign}₹{x:,.0f}"
