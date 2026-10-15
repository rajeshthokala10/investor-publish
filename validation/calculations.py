"""Pure calculation functions. Analysis uses them; recheck recomputes with them independently.

Future value = Purchase price x (1 + annual growth rate) ^ years
"""
from __future__ import annotations


def future_value(price: float, rate_pct: float, years: float) -> float:
    return price * (1 + rate_pct / 100) ** years


def cumulative_pct(rate_pct: float, years: float) -> float:
    return ((1 + rate_pct / 100) ** years - 1) * 100


def cagr_from_total(total_pct: float, years: float) -> float:
    """'Up 62% in 5 years' -> 10.1% a year."""
    if years <= 0:
        raise ValueError("years must be positive")
    return ((1 + total_pct / 100) ** (1 / years) - 1) * 100


def real_rate(nominal_pct: float, inflation_pct: float) -> float:
    return ((1 + nominal_pct / 100) / (1 + inflation_pct / 100) - 1) * 100


def emi(principal: float, annual_rate_pct: float, years: int) -> float:
    r = annual_rate_pct / 1200
    n = years * 12
    if r == 0:
        return principal / n
    return principal * r * (1 + r) ** n / ((1 + r) ** n - 1)


def loan_balance(principal: float, annual_rate_pct: float, years: int, paid_months: int) -> float:
    r = annual_rate_pct / 1200
    e = emi(principal, annual_rate_pct, years)
    if r == 0:
        return max(principal - e * paid_months, 0.0)
    return max(principal * (1 + r) ** paid_months - e * ((1 + r) ** paid_months - 1) / r, 0.0)


def illustrative_investment(cfg: dict, property_type: str, growth_pct: float, years: int,
                            gross_yield_pct: float | None, under_construction: bool = False,
                            inflation_pct: float = 4.5) -> dict:
    """Illustrative, cost-aware outcome of one purchase. Every input is an explicit assumption."""
    p = cfg["purchase_price_inr"]
    acq_pct = cfg["stamp_duty_pct"] + cfg["registration_fee_pct"] + cfg["legal_and_misc_pct"]
    if property_type == "apartment" and under_construction:
        acq_pct += cfg["gst_pct_under_construction_apartment"]
    acquisition = p * acq_pct / 100
    sale_price = future_value(p, growth_pct, years)
    selling = sale_price * cfg["brokerage_on_sale_pct"] / 100

    holding, rent_net = 0.0, 0.0
    value = p
    for _ in range(years):
        holding += value * cfg["annual_costs_pct_of_value"][property_type] / 100
        if gross_yield_pct and property_type != "plot":
            gross = value * gross_yield_pct / 100 * (12 - cfg["vacancy_months_per_year"]) / 12
            rent_net += gross * (1 - cfg["rent_collection_costs_pct_of_rent"] / 100)
        value *= 1 + growth_pct / 100

    fin = cfg["financing"]
    interest = 0.0
    equity = p + acquisition
    if fin["enabled"]:
        loan = p * fin["ltv_pct"] / 100
        e = emi(loan, fin["interest_rate_pct"], fin["tenure_years"])
        months = min(years, fin["tenure_years"]) * 12
        bal = loan_balance(loan, fin["interest_rate_pct"], fin["tenure_years"], months)
        interest = e * months - (loan - bal)
        equity = p - loan + acquisition

    capital_gain = sale_price - p
    net_profit = capital_gain + rent_net - acquisition - selling - holding - interest
    total_outlay = p + acquisition
    nominal_net_cagr = ((total_outlay + net_profit) / total_outlay) ** (1 / years) - 1 if total_outlay + net_profit > 0 else -1
    return {
        "years": years, "growth_pct": growth_pct, "purchase_price": round(p),
        "acquisition_costs": round(acquisition), "sale_price": round(sale_price),
        "selling_costs": round(selling), "holding_costs": round(holding),
        "net_rent": round(rent_net), "financing_interest": round(interest),
        "net_profit": round(net_profit), "equity_invested": round(equity),
        "net_return_on_outlay_pct_pa": round(nominal_net_cagr * 100, 1),
        "real_net_return_pct_pa": round(real_rate(nominal_net_cagr * 100, inflation_pct), 1),
    }
