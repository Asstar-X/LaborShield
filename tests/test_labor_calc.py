"""Unit tests for tools/labor_calc.py covering statutory boundaries and edge cases."""

from __future__ import annotations

from tools.labor_calc import (
    calc_annual_leave_pay,
    calc_overtime_pay,
    calc_service_years,
    calc_severance_or_damages,
    calc_unwritten_contract_double_wage,
    calculate_case,
)


def test_service_years_rounding_under_and_over_six_months() -> None:
    # Less than 6 months: 2024-03-01 to 2024-06-15 -> 3 months 15 days -> N = 0.5
    res_half = calc_service_years("2024-03-01", "2024-06-15")
    assert res_half["years"] == 0
    assert res_half["n_un_capped"] == 0.5

    # Exactly 6 months: 2024-01-01 to 2024-06-30 -> 6 months 0 days -> N = 1.0
    res_six = calc_service_years("2024-01-01", "2024-06-30")
    assert res_six["months"] == 6
    assert res_six["n_un_capped"] == 1.0

    # 3 years 3 months 6 days -> N = 3.5
    res_three_half = calc_service_years("2021-05-10", "2024-08-15")
    assert res_three_half["years"] == 3
    assert res_three_half["months"] == 3
    assert res_three_half["n_un_capped"] == 3.5


def test_3x_cap_and_12_year_limit_linkage() -> None:
    # Case A: Tenure = 15 years, Wage = 15,000 <= 3x Cap (Shenzhen 3x = 43,659)
    # CRITICAL STATUTORY RULE: Should NOT cap tenure at 12 years when wage <= 3x cap!
    uncapped = calc_severance_or_damages(
        mode="2N",
        avg_wage=15000,
        n_value=15.0,
        soc_avg_monthly=14553,
        min_wage_monthly=2520,
    )
    assert uncapped["is_3x_capped"] is False
    assert uncapped["n_used"] == 15.0
    assert uncapped["main_amount"] == 15000.0 * 15.0 * 2

    # Case B: Tenure = 15 years, Wage = 50,000 > 3x Cap (Shenzhen 3x = 43,659)
    # Both wage base (43,659) AND tenure (max 12 years) must be capped!
    capped = calc_severance_or_damages(
        mode="2N",
        avg_wage=50000,
        n_value=15.0,
        soc_avg_monthly=14553,
        min_wage_monthly=2520,
    )
    assert capped["is_3x_capped"] is True
    assert capped["base_wage_used"] == 43659.0
    assert capped["n_used"] == 12.0
    assert capped["main_amount"] == round(43659.0 * 12.0 * 2, 2)


def test_notice_pay_plus_one_exclusivity_and_uncapped_base() -> None:
    # In N+1 (Article 40), +1 uses last_month_wage uncapped by 3x social average
    res_n1 = calc_severance_or_damages(
        mode="N+1",
        avg_wage=50000,
        n_value=2.0,
        soc_avg_monthly=14553,
        min_wage_monthly=2520,
        last_month_wage=52000,
    )
    assert res_n1["main_amount"] == 43659.0 * 2.0
    assert res_n1["notice_pay_amount"] == 52000.0

    # In 2N (Article 87), attempting to include +1 triggers statutory conflict guard and zeroes notice_pay
    res_2n = calc_severance_or_damages(
        mode="2N",
        avg_wage=18000,
        n_value=3.5,
        soc_avg_monthly=14553,
        min_wage_monthly=2520,
        include_notice_pay=True,
    )
    assert res_2n["notice_pay_amount"] == 0.0
    assert len(res_2n["statutory_conflicts"]) == 1


def test_unwritten_contract_double_wage_11_month_cap() -> None:
    res = calc_unwritten_contract_double_wage(unwritten_months=14, monthly_wage_base=10000)
    assert res["months_claimed"] == 11.0
    assert res["amount"] == 110000.0


def test_annual_leave_proration_floor_and_200_percent() -> None:
    # Cumulative work years = 5 -> 5 statutory days/year.
    # Worked 200 days in termination year: floor(200/365 * 5) = floor(2.739) = 2 days.
    res = calc_annual_leave_pay(
        avg_wage=21750,
        cumulative_work_years=5,
        days_worked_in_termination_year=200,
        days_already_taken=0,
    )
    assert res["untaken_days"] == 2.0
    assert res["daily_wage"] == 1000.0
    assert res["amount"] == 4000.0  # 1000/day * 2 days * 200%


def test_overtime_pay_three_tiers() -> None:
    # Base = 21,750 -> daily = 1,000 -> hourly = 125.00
    res = calc_overtime_pay(
        overtime_wage_base=21750,
        weekday_hours=8,    # 8 * 125 * 1.5 = 1,500
        weekend_hours=16,   # 16 * 125 * 2.0 = 4,000
        holiday_hours=8,    # 8 * 125 * 3.0 = 3,000
        already_paid_overtime=500,
    )
    assert res["hourly_base"] == 125.0
    assert res["amount"] == 8000.0


def test_article_47_finality_per_claim_classification() -> None:
    result = calculate_case(
        {
            "city": "深圳",
            "start_date": "2021-05-10",
            "end_date": "2024-08-15",
            "avg_wage": 18000,
            "termination_mode": "2N",
            "unpaid_wages_amount": 9103.45,
            "untaken_leave_days": 4,
            "overtime_weekend_hours": 20,
        }
    )
    claims = result["article_47_finality"]["claims"]
    assert len(claims) == 4
    # Claim 1 (2N = 126,000) > 30,240 -> non-final
    assert claims[0]["is_article_47_final"] is False
    # Claims 2, 3, 4 are each <= 30,240 -> Article 47 final!
    assert claims[1]["is_article_47_final"] is True
    assert claims[2]["is_article_47_final"] is True
    assert claims[3]["is_article_47_final"] is True
    assert result["grand_total"] == 145862.07
