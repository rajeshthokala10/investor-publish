import math

import pytest

from analysis.prices import comparable, normalise_price, parse_unit
from validation.calculations import (cagr_from_total, cumulative_pct, emi, future_value, illustrative_investment,
                                     loan_balance, real_rate)
from harness.common import load_config


def test_unit_parsing():
    assert parse_unit("INR/sqft") == (1.0, "sqft")
    assert parse_unit("INR crore/acre") == (1e7, "acre")
    assert parse_unit("Rs lakh") == (1e5, None)
    assert parse_unit("₹ per sq yd") == (1.0, "sqyd")


def test_sqyd_land_rate_normalises_to_psf():
    n = normalise_price(45000, "INR/sqyd", "land", "developer_quote")
    assert n["psf_inr"] == 5000
    assert n["comparability"] == "land_rate|developer_quote"


def test_acre_rate():
    n = normalise_price(4.356, "INR crore/acre", "land", "reported_transaction")
    assert n["psf_inr"] == pytest.approx(1000, rel=1e-6)


def test_total_price_is_not_psf():
    n = normalise_price(1.2, "INR crore", "super_built_up", "asking")
    assert n["psf_inr"] is None and n["total_inr"] == 12_000_000


def test_land_and_saleable_rates_are_never_comparable():
    plot = normalise_price(5000, "INR/sqft", "land", "developer_quote")
    apt = normalise_price(5000, "INR/sqft", "super_built_up", "developer_quote")
    apt2 = normalise_price(9000, "INR/sqft", "super_built_up", "developer_quote")
    unknown = normalise_price(9000, "INR/sqft", "unknown", "developer_quote")
    asking = normalise_price(9000, "INR/sqft", "super_built_up", "asking")
    assert not comparable(plot, apt)
    assert comparable(apt, apt2)
    assert not comparable(apt, unknown)
    assert not comparable(apt, asking)          # asking prices are not developer quotes


def test_growth_formulas():
    assert future_value(10_000_000, 8, 5) == pytest.approx(10_000_000 * 1.08 ** 5)
    assert cumulative_pct(10, 3) == pytest.approx(33.1)
    assert cagr_from_total(50, 5) == pytest.approx((1.5 ** 0.2 - 1) * 100)
    assert real_rate(7, 4.5) == pytest.approx((1.07 / 1.045 - 1) * 100)
    with pytest.raises(ValueError):
        cagr_from_total(50, 0)


def test_emi_and_balance():
    e = emi(1_000_000, 8.5, 20)
    assert e == pytest.approx(8678.23, abs=0.01)
    assert loan_balance(1_000_000, 8.5, 20, 240) == pytest.approx(0, abs=1)
    assert loan_balance(1_000_000, 8.5, 20, 0) == pytest.approx(1_000_000)


def test_illustration_adds_up():
    cfg = load_config("scoring")["illustrative_investment"]
    r = illustrative_investment(cfg, "apartment", 6.0, 5, 3.0)
    recomposed = (r["sale_price"] - r["purchase_price"] + r["net_rent"] - r["acquisition_costs"]
                  - r["selling_costs"] - r["holding_costs"] - r["financing_interest"])
    assert abs(recomposed - r["net_profit"]) <= 3          # rounding of components only
    plot = illustrative_investment(cfg, "plot", 6.0, 5, 3.0)
    assert plot["net_rent"] == 0                           # plots earn no rent in the model
    assert r["real_net_return_pct_pa"] < r["net_return_on_outlay_pct_pa"]
