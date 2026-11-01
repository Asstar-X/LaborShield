#!/usr/bin/env python3
"""Deterministic China Labor & Personnel Dispute Arbitration Calculator (LaborShield).

Implements exact statutory calculations under PRC Labor Contract Law, Labor Law,
Labor Dispute Mediation and Arbitration Law (Article 47 Finality), and Paid Annual
Leave Regulations using Decimal (ROUND_HALF_UP) to eliminate LLM arithmetic drift.

Usage:
  python3 tools/labor_calc.py --input case_input.json --json --output dockets/calc_result.json
  python3 tools/labor_calc.py --city 深圳 --start-date 2021-03-15 --end-date 2024-08-20 \
      --avg-wage 18000 --mode 2N --untaken-leave-days 4 --json
"""

from __future__ import annotations

import argparse
import calendar
import json
import math
import re
import sys
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

# Statutory monthly working days for daily wage conversion (劳社部发〔2008〕3号)
MONTHLY_PAY_DAYS = Decimal("21.75")
DAILY_WORK_HOURS = Decimal("8")

# Built-in city statutory benchmarks (Unit: RMB/month)
# Users or profiles can always override `soc_avg_monthly` and `min_wage_monthly`.
CITY_BENCHMARKS: dict[str, dict[str, Any]] = {
    "北京": {
        "soc_avg_monthly": Decimal("11937.00"),
        "min_wage_monthly": Decimal("2420.00"),
        "region_note": "北京市人社局社平工资及月最低工资标准基准",
    },
    "上海": {
        "soc_avg_monthly": Decimal("12307.00"),
        "min_wage_monthly": Decimal("2690.00"),
        "region_note": "上海市人社局社平工资及月最低工资标准基准",
    },
    "深圳": {
        "soc_avg_monthly": Decimal("14553.00"),
        "min_wage_monthly": Decimal("2520.00"),
        "region_note": "深圳市人社局社平工资及全日制月最低工资标准基准",
    },
    "广州": {
        "soc_avg_monthly": Decimal("13169.00"),
        "min_wage_monthly": Decimal("2500.00"),
        "region_note": "广州市人社局社平工资及月最低工资标准基准",
    },
    "杭州": {
        "soc_avg_monthly": Decimal("11303.00"),
        "min_wage_monthly": Decimal("2490.00"),
        "region_note": "杭州市市区社平工资及月最低工资标准基准",
    },
    "成都": {
        "soc_avg_monthly": Decimal("9145.00"),
        "min_wage_monthly": Decimal("2100.00"),
        "region_note": "成都市社平工资及中心城区月最低工资标准基准",
    },
    "苏州": {
        "soc_avg_monthly": Decimal("10953.00"),
        "min_wage_monthly": Decimal("2490.00"),
        "region_note": "苏州市一类地区社平工资及月最低工资标准基准",
    },
    "武汉": {
        "soc_avg_monthly": Decimal("9641.00"),
        "min_wage_monthly": Decimal("2210.00"),
        "region_note": "武汉市主城区社平工资及月最低工资标准基准",
    },
}

LAW_2008_EFFECTIVE_DATE = date(2008, 1, 1)


def to_dec(val: Any) -> Decimal:
    if isinstance(val, Decimal):
        return val
    if val is None or val == "":
        return Decimal("0.00")
    return Decimal(str(val))


def money(val: Any) -> Decimal:
    """Round to 2 decimal places using standard financial ROUND_HALF_UP."""
    return to_dec(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_date(d_str: str | date) -> date:
    if isinstance(d_str, date):
        return d_str
    cleaned = str(d_str).strip().replace(".", "-").replace("/", "-")
    return datetime.strptime(cleaned, "%Y-%m-%d").date()


def add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        # Handle Feb 29 -> Feb 28 in non-leap year
        return d.replace(year=d.year + years, day=28)


def add_months(d: date, months: int) -> date:
    total_months = (d.year * 12 + (d.month - 1)) + months
    new_year = total_months // 12
    new_month = (total_months % 12) + 1
    max_day = calendar.monthrange(new_year, new_month)[1]
    return date(new_year, new_month, min(d.day, max_day))


def calc_period_years_months_days(start: date, end: date) -> tuple[int, int, int]:
    """Calculate exact (years, months, days) for an inclusive employment period [start, end].

    In Chinese labor arbitration practice, e.g. 2023-03-01 to 2024-02-29 is 1 full year
    (because 2024-02-29 + 1 day == 2024-03-01). We evaluate against `end_exclusive = end + 1 day`.
    """
    if end < start:
        raise ValueError(f"end_date ({end}) cannot be earlier than start_date ({start})")
    end_excl = date.fromordinal(end.toordinal() + 1)

    years = end_excl.year - start.year
    if (end_excl.month, end_excl.day) < (start.month, start.day):
        years -= 1

    anniv = add_years(start, years)
    months = 0
    while True:
        next_m = add_months(anniv, months + 1)
        if next_m <= end_excl:
            months += 1
        else:
            break

    month_anchor = add_months(anniv, months)
    days = (end_excl - month_anchor).days
    return years, months, days


def years_to_n(years: int, months: int, days: int) -> Decimal:
    """Convert (years, months, days) to statutory N under Labor Contract Law Art. 47.

    Rule: Every full year = 1.0; >= 6 months and < 1 year = 1.0; < 6 months (if > 0) = 0.5.
    """
    if years == 0 and months == 0 and days == 0:
        return Decimal("0.0")
    base_n = Decimal(years)
    if months > 6 or (months == 6 and days >= 0):
        return base_n + Decimal("1.0")
    if months > 0 or days > 0:
        return base_n + Decimal("0.5")
    return base_n


def calc_service_years(
    start_date: str | date,
    end_date: str | date,
    prior_affiliated_years: float | Decimal = 0,
) -> dict[str, Any]:
    """Compute tenure details, statutory N, and pre/post-2008 breakdown."""
    s_date = parse_date(start_date)
    e_date = parse_date(end_date)
    years, months, days = calc_period_years_months_days(s_date, e_date)
    raw_n = years_to_n(years, months, days) + to_dec(prior_affiliated_years)

    has_pre_2008 = s_date < LAW_2008_EFFECTIVE_DATE
    pre_2008_n = Decimal("0.0")
    post_2008_n = raw_n
    if has_pre_2008:
        if e_date < LAW_2008_EFFECTIVE_DATE:
            pre_2008_n = raw_n
            post_2008_n = Decimal("0.0")
        else:
            pre_end = date(2007, 12, 31)
            py, pm, pd = calc_period_years_months_days(s_date, pre_end)
            # Pre-2008 rule under 违反和解除劳动合同的经济补偿办法: < 6 months was also 0.5 or 1 depending on cause,
            # standard unified representation uses half-year rounding or full-year rounding.
            pre_2008_n = years_to_n(py, pm, pd)
            post_y, post_m, post_d = calc_period_years_months_days(LAW_2008_EFFECTIVE_DATE, e_date)
            post_2008_n = years_to_n(post_y, post_m, post_d) + to_dec(prior_affiliated_years)

    return {
        "start_date": s_date.isoformat(),
        "end_date": e_date.isoformat(),
        "total_calendar_days": (e_date - s_date).days + 1,
        "years": years,
        "months": months,
        "days": days,
        "prior_affiliated_years": float(to_dec(prior_affiliated_years)),
        "n_un_capped": float(raw_n),
        "has_pre_2008_tenure": has_pre_2008,
        "pre_2008_n": float(pre_2008_n),
        "post_2008_n": float(post_2008_n),
        "tenure_description": f"{years}年{months}个月{days}天（折算工龄系数 N = {raw_n}）",
    }


def calc_average_wage(
    monthly_wages: list[float | Decimal] | None = None,
    avg_wage_override: float | Decimal | None = None,
    annual_bonus_prorated: float | Decimal = 0,
    min_wage_monthly: float | Decimal = 0,
) -> dict[str, Any]:
    """Calculate the 12-month pre-termination average gross wage (应得工资)."""
    min_w = money(min_wage_monthly)
    bonus_monthly = money(to_dec(annual_bonus_prorated) / Decimal("12")) if to_dec(annual_bonus_prorated) > 0 else Decimal("0.00")

    if monthly_wages and len(monthly_wages) > 0:
        wages_dec = [money(w) for w in monthly_wages[:12]]
        months_count = len(wages_dec)
        total_wages = sum(wages_dec, Decimal("0.00"))
        raw_avg = money(total_wages / Decimal(months_count)) + bonus_monthly
    elif avg_wage_override is not None:
        months_count = 12
        total_wages = money(avg_wage_override) * Decimal("12")
        raw_avg = money(avg_wage_override) + bonus_monthly
    else:
        months_count = 0
        total_wages = Decimal("0.00")
        raw_avg = Decimal("0.00")

    below_min_wage = raw_avg > 0 and raw_avg < min_w
    effective_avg = max(raw_avg, min_w) if raw_avg > 0 else Decimal("0.00")

    return {
        "months_counted": months_count,
        "total_gross_wages": float(total_wages),
        "monthly_bonus_prorated": float(bonus_monthly),
        "raw_avg_wage": float(raw_avg),
        "min_wage_floor_applied": below_min_wage,
        "effective_avg_wage": float(effective_avg),
    }


def calc_severance_or_damages(
    mode: str,
    avg_wage: float | Decimal,
    n_value: float | Decimal,
    soc_avg_monthly: float | Decimal,
    min_wage_monthly: float | Decimal,
    last_month_wage: float | Decimal | None = None,
    include_notice_pay: bool = False,
    forced_termination_notice_sent: bool = True,
    resignation_reason_is_personal: bool = False,
) -> dict[str, Any]:
    """Calculate 2N (illegal termination), N (economic severance), or N+1 (Art. 40).

    Enforces the critical statutory linkage:
    - 12-year tenure cap ONLY applies when `avg_wage > 3 * soc_avg_monthly`.
    - `+1` notice pay ONLY applies to Article 40 (`N+1`) and uses `last_month_wage` uncapped.
    """
    norm_mode = mode.strip().upper()
    w_avg = max(money(avg_wage), money(min_wage_monthly)) if to_dec(avg_wage) > 0 else Decimal("0.00")
    n_raw = to_dec(n_value)
    cap_3x = money(to_dec(soc_avg_monthly) * Decimal("3"))
    last_w = money(last_month_wage) if last_month_wage is not None else money(avg_wage)

    warnings: list[str] = []
    statutory_conflicts: list[str] = []

    if resignation_reason_is_personal and norm_mode in ("2N", "N", "N+1", "FORCED_N"):
        warnings.append(
            "【高危红灯】劳动者在离职文件或沟通中自认“个人原因辞职”，主张经济补偿金(N)或赔偿金(2N)面临极高败诉风险，除非有确凿证据证明系受欺诈、胁迫或用人单位存在《劳动合同法》第38条过错且已即时推翻。"
        )

    if norm_mode == "FORCED_N" and not forced_termination_notice_sent:
        warnings.append(
            "【程序瑕疵警告】主张《劳动合同法》第38条被迫解除劳动合同经济补偿金(N)，必须向用人单位正式送达载明被迫解除事由的《被迫解除劳动合同通知书》（如EMS邮寄回执或微信明确告知）。"
        )

    # 3x Social Average Wage Cap & 12-Year Tenure Cap Linkage
    if cap_3x > 0 and w_avg > cap_3x:
        is_3x_capped = True
        base_used = cap_3x
        n_used = min(n_raw, Decimal("12.0"))
        cap_explanation = (
            f"离职前12个月平均应得工资（{w_avg}元）高于当地上年度职工月平均工资3倍（{cap_3x}元），"
            f"依法按3倍封顶基数（{base_used}元）计算，且计算年限最高不超过12年（核定年限系数 N={n_used}）。"
        )
    else:
        is_3x_capped = False
        base_used = w_avg
        n_used = n_raw
        cap_explanation = (
            f"离职前12个月平均应得工资（{w_avg}元）未超过当地社平工资3倍（{cap_3x}元），"
            f"按实际平均应得工资基数（{base_used}元）及实际折算年限（N={n_used}，不受12年封顶限制）计算。"
        )

    notice_pay_amount = Decimal("0.00")
    if norm_mode == "2N":
        if include_notice_pay:
            statutory_conflicts.append(
                "【法定排他拦截】主张《劳动合同法》第87条违法解除赔偿金(2N)时，在法律逻辑上排斥第40条合法解除之代通知金(+1)，已自动剔除+1项以防立案退回。"
            )
        main_amount = money(base_used * n_used * Decimal("2"))
        claim_title = "违法解除劳动合同赔偿金（2N）"
        legal_basis = "《中华人民共和国劳动合同法》第四十七条、第八十七条"
        formula_str = f"{base_used}元/月 × {n_used}个月 × 2倍 = {main_amount}元"
    elif norm_mode == "N+1":
        main_amount = money(base_used * n_used)
        notice_pay_amount = last_w
        claim_title = "解除劳动合同经济补偿金（N）及未提前三十日书面通知代通知金（+1）"
        legal_basis = "《中华人民共和国劳动合同法》第四十条、第四十六条、第四十七条；《劳动合同法实施条例》第二十条"
        formula_str = (
            f"经济补偿金：{base_used}元/月 × {n_used}个月 = {main_amount}元；"
            f"代通知金（按上月工资标准）：{notice_pay_amount}元 × 1个月 = {notice_pay_amount}元"
        )
    elif norm_mode in ("N", "FORCED_N"):
        if include_notice_pay:
            statutory_conflicts.append(
                "【法定排他拦截】代通知金(+1)仅适用于《劳动合同法》第40条无过失性辞退情形；被迫解除(第38条)、协商解除(第36条)或经济性裁员(第41条)均不适用代通知金(+1)，已自动剔除。"
            )
        main_amount = money(base_used * n_used)
        claim_title = (
            "被迫解除劳动合同经济补偿金（N）" if norm_mode == "FORCED_N" else "解除/终止劳动合同经济补偿金（N）"
        )
        legal_basis = (
            "《中华人民共和国劳动合同法》第三十八条、第四十六条、第四十七条"
            if norm_mode == "FORCED_N"
            else "《中华人民共和国劳动合同法》第四十六条、第四十七条"
        )
        formula_str = f"{base_used}元/月 × {n_used}个月 = {main_amount}元"
    elif norm_mode in ("NONE", "CONTINUE"):
        main_amount = Decimal("0.00")
        claim_title = "继续履行劳动合同（不主张解除赔偿金/补偿金）" if norm_mode == "CONTINUE" else "无解除类经济诉求"
        legal_basis = "《中华人民共和国劳动合同法》第四十八条"
        formula_str = "0.00元"
    else:
        raise ValueError(f"Unsupported termination calculation mode: {mode!r}. Expected 2N, N, N+1, FORCED_N, CONTINUE, or NONE.")

    return {
        "mode": norm_mode,
        "claim_title": claim_title,
        "base_wage_used": float(base_used),
        "n_raw": float(n_raw),
        "n_used": float(n_used),
        "is_3x_capped": is_3x_capped,
        "cap_3x_threshold": float(cap_3x),
        "cap_explanation": cap_explanation,
        "main_amount": float(main_amount),
        "notice_pay_amount": float(notice_pay_amount),
        "total_termination_amount": float(main_amount + notice_pay_amount),
        "formula": formula_str,
        "legal_basis": legal_basis,
        "warnings": warnings,
        "statutory_conflicts": statutory_conflicts,
    }


def calc_unwritten_contract_double_wage(
    unwritten_months: float | Decimal = 0,
    monthly_wage_base: float | Decimal = 0,
    monthly_wages_in_window: list[float | Decimal] | None = None,
) -> dict[str, Any]:
    """Calculate double wage difference for failing to sign a written labor contract (Art. 82).

    Window: From day after 1 full month of employment up to 1 full year (max 11 months).
    """
    if monthly_wages_in_window and len(monthly_wages_in_window) > 0:
        capped_wages = [money(w) for w in monthly_wages_in_window[:11]]
        months_used = Decimal(len(capped_wages))
        amount = money(sum(capped_wages, Decimal("0.00")))
        formula = f"未签书面劳动合同窗口期（{months_used}个月）实发/应发工资总和 × 100% = {amount}元"
    else:
        raw_m = to_dec(unwritten_months)
        months_used = min(max(raw_m, Decimal("0.0")), Decimal("11.0"))
        w_base = money(monthly_wage_base)
        amount = money(w_base * months_used)
        formula = f"{w_base}元/月 × {months_used}个月 × 100%（二倍工资差额） = {amount}元"

    return {
        "claim_title": "未订立书面劳动合同二倍工资差额",
        "months_claimed": float(months_used),
        "max_statutory_months": 11.0,
        "amount": float(amount),
        "formula": formula,
        "legal_basis": "《中华人民共和国劳动合同法》第八十二条第一款；《劳动合同法实施条例》第六条、第七条",
    }


def calc_annual_leave_pay(
    avg_wage: float | Decimal,
    untaken_days: float | Decimal | None = None,
    cumulative_work_years: float | Decimal | None = None,
    days_worked_in_termination_year: int | None = None,
    days_already_taken: float | Decimal = 0,
) -> dict[str, Any]:
    """Calculate untaken paid annual leave compensation (200% additional difference).

    Rule under《企业职工带薪年休假实施办法》第12条:
    Prorated days = floor((days_worked_in_termination_year / 365) * statutory_days) - days_already_taken.
    Fractional days (< 1 full day) are discarded via math.floor.
    """
    w_avg = money(avg_wage)
    daily_wage = money(w_avg / MONTHLY_PAY_DAYS) if w_avg > 0 else Decimal("0.00")

    statutory_days = 0
    if cumulative_work_years is not None:
        cy = to_dec(cumulative_work_years)
        if cy >= Decimal("20"):
            statutory_days = 15
        elif cy >= Decimal("10"):
            statutory_days = 10
        elif cy >= Decimal("1"):
            statutory_days = 5
        else:
            statutory_days = 0

    if untaken_days is not None:
        effective_untaken = max(Decimal("0"), to_dec(untaken_days))
        proration_note = f"按确认未休年休假天数 {effective_untaken} 天核算"
    elif days_worked_in_termination_year is not None and statutory_days > 0:
        prorated_entitled = math.floor((days_worked_in_termination_year / 365.0) * statutory_days)
        effective_untaken = max(Decimal("0"), Decimal(prorated_entitled) - to_dec(days_already_taken))
        proration_note = (
            f"累计工龄对应法定年假 {statutory_days} 天；离职当年在职 {days_worked_in_termination_year} 天，"
            f"折算应休 floor({days_worked_in_termination_year}/365 × {statutory_days}) = {prorated_entitled} 天（不足1整天部分依法舍去），"
            f"扣除已休 {days_already_taken} 天，应补未休年假 {effective_untaken} 天"
        )
    else:
        effective_untaken = Decimal("0")
        proration_note = "无未休带薪年休假诉求"

    # Unpaid difference is 200% (since 100% regular salary was paid during working days)
    amount = money((w_avg / MONTHLY_PAY_DAYS) * effective_untaken * Decimal("2"))

    return {
        "claim_title": "未休带薪年休假工资报酬差额（200%部分）",
        "daily_wage": float(daily_wage),
        "untaken_days": float(effective_untaken),
        "proration_note": proration_note,
        "amount": float(amount),
        "formula": f"（{w_avg}元 ÷ 21.75天）× {effective_untaken}天 × 200% = {amount}元",
        "legal_basis": "《职工带薪年休假条例》第三条、第五条；《企业职工带薪年休假实施办法》第十条、第十一条、第十二条",
    }


def calc_overtime_pay(
    overtime_wage_base: float | Decimal,
    weekday_hours: float | Decimal = 0,
    weekend_hours: float | Decimal = 0,
    holiday_hours: float | Decimal = 0,
    already_paid_overtime: float | Decimal = 0,
) -> dict[str, Any]:
    """Calculate overtime pay across weekday (150%), weekend (200%), and statutory holiday (300%)."""
    base = money(overtime_wage_base)
    wk_h = to_dec(weekday_hours)
    we_h = to_dec(weekend_hours)
    ho_h = to_dec(holiday_hours)
    paid = money(already_paid_overtime)

    if base <= 0 or (wk_h == 0 and we_h == 0 and ho_h == 0):
        return {
            "claim_title": "加班工资差额",
            "overtime_wage_base": float(base),
            "hourly_base": 0.0,
            "weekday_hours": 0.0,
            "weekend_hours": 0.0,
            "holiday_hours": 0.0,
            "weekday_amount": 0.0,
            "weekend_amount": 0.0,
            "holiday_amount": 0.0,
            "already_paid_overtime": float(paid),
            "amount": 0.0,
            "formula": "0.00元",
            "legal_basis": "《中华人民共和国劳动法》第四十四条",
        }

    hourly_exact = base / MONTHLY_PAY_DAYS / DAILY_WORK_HOURS
    hourly_display = money(hourly_exact)
    wk_amt = money(hourly_exact * wk_h * Decimal("1.5"))
    we_amt = money(hourly_exact * we_h * Decimal("2.0"))
    ho_amt = money(hourly_exact * ho_h * Decimal("3.0"))
    net_amount = max(Decimal("0.00"), wk_amt + we_amt + ho_amt - paid)

    parts = []
    if wk_h > 0:
        parts.append(f"延时加班：{ base }÷21.75÷8×{wk_h}小时×150%={wk_amt}元")
    if we_h > 0:
        parts.append(f"休息日加班：{ base }÷21.75÷8×{we_h}小时×200%={we_amt}元")
    if ho_h > 0:
        parts.append(f"法定节假日加班：{ base }÷21.75÷8×{ho_h}小时×300%={ho_amt}元")
    if paid > 0:
        parts.append(f"扣减已发加班费：{paid}元")

    return {
        "claim_title": "加班工资差额",
        "overtime_wage_base": float(base),
        "hourly_base": float(hourly_display),
        "weekday_hours": float(wk_h),
        "weekend_hours": float(we_h),
        "holiday_hours": float(ho_h),
        "weekday_amount": float(wk_amt),
        "weekend_amount": float(we_amt),
        "holiday_amount": float(ho_amt),
        "already_paid_overtime": float(paid),
        "amount": float(net_amount),
        "formula": "；".join(parts) + f" → 合计应补差额：{net_amount}元",
        "legal_basis": "《中华人民共和国劳动法》第四十四条；《最高人民法院关于审理劳动争议案件适用法律问题的解释（一）》第四十二条",
    }


def classify_article_47_finality(
    claim_items: list[dict[str, Any]],
    min_wage_monthly: float | Decimal,
) -> dict[str, Any]:
    """Evaluate each claim item against Article 47 Finality (一裁终局) threshold.

    Threshold = 12 * local monthly minimum wage.
    Per SPC Interpretation I Art. 20, finality is assessed per individual claim category.
    """
    threshold = money(to_dec(min_wage_monthly) * Decimal("12"))
    evaluated_items = []
    all_final = True

    for idx, item in enumerate(claim_items, start=1):
        amt = money(item.get("amount", 0))
        category = item.get("category", "monetary")
        is_statutory_47_type = category in (
            "labor_remuneration",
            "severance_or_damages",
            "medical_injury",
        )
        is_final = is_statutory_47_type and (amt <= threshold)
        if not is_final:
            all_final = False
        evaluated_items.append(
            {
                "index": idx,
                "title": item["title"],
                "category": category,
                "amount": float(amt),
                "formula": item["formula"],
                "legal_basis": item["legal_basis"],
                "is_article_47_final": is_final,
                "finality_tag": (
                    f"【一裁终局项】单项未超当地12个月最低工资标准（≤{threshold}元）"
                    if is_final
                    else f"【非终局项】单项超过当地12个月最低工资标准（>{threshold}元）或属非终局确认之诉"
                ),
            }
        )

    strategy_advice = (
        f"本案全部请求单项金额均不超过当地月最低工资标准十二个月之和（{threshold}元），"
        "依法适用《劳动争议调解仲裁法》第四十七条“一裁终局”制度：裁决书自作出之日起生效，被申请人（用人单位）无权向基层人民法院起诉！"
        if (evaluated_items and all_final)
        else (
            f"当地一裁终局单项阈值为 {threshold} 元（月最低工资 {money(min_wage_monthly)} 元 × 12）。"
            "已将各项仲裁请求按法定性质独立分项列明，确保低于阈值的独立请求项最大化争取一裁终局审查。"
        )
    )

    return {
        "threshold_12x_min_wage": float(threshold),
        "all_claims_final": bool(evaluated_items and all_final),
        "claims": evaluated_items,
        "strategy_advice": strategy_advice,
    }


def calculate_case(data: dict[str, Any]) -> dict[str, Any]:
    """Master entry point to compute full labor arbitration claims from a structured case dict."""
    city = str(data.get("city", "深圳")).strip().replace("市", "")
    bench = CITY_BENCHMARKS.get(city, CITY_BENCHMARKS["深圳"])
    soc_avg = money(data.get("soc_avg_monthly") or bench["soc_avg_monthly"])
    min_wage = money(data.get("min_wage_monthly") or bench["min_wage_monthly"])

    tenure = calc_service_years(
        start_date=data["start_date"],
        end_date=data["end_date"],
        prior_affiliated_years=data.get("prior_affiliated_years", 0),
    )

    wage_info = calc_average_wage(
        monthly_wages=data.get("monthly_wages"),
        avg_wage_override=data.get("avg_wage"),
        annual_bonus_prorated=data.get("annual_bonus_prorated", 0),
        min_wage_monthly=min_wage,
    )
    eff_avg_wage = to_dec(wage_info["effective_avg_wage"])

    term_info = calc_severance_or_damages(
        mode=data.get("termination_mode", data.get("mode", "2N")),
        avg_wage=eff_avg_wage,
        n_value=tenure["n_un_capped"],
        soc_avg_monthly=soc_avg,
        min_wage_monthly=min_wage,
        last_month_wage=data.get("last_month_wage"),
        include_notice_pay=bool(data.get("include_notice_pay", False)),
        forced_termination_notice_sent=bool(data.get("forced_termination_notice_sent", True)),
        resignation_reason_is_personal=bool(data.get("resignation_reason_is_personal", False)),
    )

    double_wage_info = calc_unwritten_contract_double_wage(
        unwritten_months=data.get("unwritten_contract_months", 0),
        monthly_wage_base=data.get("unwritten_contract_wage_base", eff_avg_wage),
        monthly_wages_in_window=data.get("unwritten_contract_monthly_wages"),
    )

    leave_info = calc_annual_leave_pay(
        avg_wage=eff_avg_wage,
        untaken_days=data.get("untaken_leave_days"),
        cumulative_work_years=data.get("cumulative_work_years"),
        days_worked_in_termination_year=data.get("days_worked_in_termination_year"),
        days_already_taken=data.get("days_already_taken", 0),
    )

    ot_info = calc_overtime_pay(
        overtime_wage_base=data.get("overtime_wage_base", eff_avg_wage),
        weekday_hours=data.get("overtime_weekday_hours", 0),
        weekend_hours=data.get("overtime_weekend_hours", 0),
        holiday_hours=data.get("overtime_holiday_hours", 0),
        already_paid_overtime=data.get("already_paid_overtime", 0),
    )

    unpaid_wages_amount = money(data.get("unpaid_wages_amount", 0))
    unpaid_wages_period = str(data.get("unpaid_wages_period", "在职期间拖欠工资"))

    # Build itemized claims list (strictly separated per Article 47 finality strategy)
    claim_items: list[dict[str, Any]] = []

    if to_dec(term_info["main_amount"]) > 0:
        claim_items.append(
            {
                "title": f"请求裁决被申请人向申请人支付{term_info['claim_title'].split('（')[0]}人民币 {term_info['main_amount']:.2f} 元",
                "short_title": term_info["claim_title"].split("及")[0],
                "category": "severance_or_damages",
                "amount": term_info["main_amount"],
                "formula": term_info["formula"].split("；")[0],
                "legal_basis": term_info["legal_basis"],
            }
        )
    if to_dec(term_info["notice_pay_amount"]) > 0:
        claim_items.append(
            {
                "title": f"请求裁决被申请人向申请人支付未提前三十日书面通知解除劳动合同之一个月工资（代通知金）人民币 {term_info['notice_pay_amount']:.2f} 元",
                "short_title": "未提前30日书面通知代通知金（+1）",
                "category": "severance_or_damages",
                "amount": term_info["notice_pay_amount"],
                "formula": f"上一个月应得工资标准 {term_info['notice_pay_amount']:.2f}元 × 1个月 = {term_info['notice_pay_amount']:.2f}元",
                "legal_basis": "《中华人民共和国劳动合同法》第四十条；《劳动合同法实施条例》第二十条",
            }
        )
    if unpaid_wages_amount > 0:
        claim_items.append(
            {
                "title": f"请求裁决被申请人向申请人支付{unpaid_wages_period}人民币 {unpaid_wages_amount:.2f} 元",
                "short_title": f"拖欠工资（{unpaid_wages_period}）",
                "category": "labor_remuneration",
                "amount": float(unpaid_wages_amount),
                "formula": str(data.get("unpaid_wages_formula", f"{unpaid_wages_period}应发未发总额 = {unpaid_wages_amount:.2f}元")),
                "legal_basis": "《中华人民共和国劳动合同法》第三十条第一款",
            }
        )
    if to_dec(double_wage_info["amount"]) > 0:
        claim_items.append(
            {
                "title": f"请求裁决被申请人向申请人支付未依法订立书面劳动合同二倍工资差额人民币 {double_wage_info['amount']:.2f} 元",
                "short_title": double_wage_info["claim_title"],
                "category": "severance_or_damages",
                "amount": double_wage_info["amount"],
                "formula": double_wage_info["formula"],
                "legal_basis": double_wage_info["legal_basis"],
            }
        )
    if to_dec(leave_info["amount"]) > 0:
        claim_items.append(
            {
                "title": f"请求裁决被申请人向申请人支付未休带薪年休假工资报酬差额人民币 {leave_info['amount']:.2f} 元",
                "short_title": leave_info["claim_title"],
                "category": "labor_remuneration",
                "amount": leave_info["amount"],
                "formula": leave_info["formula"],
                "legal_basis": leave_info["legal_basis"],
            }
        )
    if to_dec(ot_info["amount"]) > 0:
        claim_items.append(
            {
                "title": f"请求裁决被申请人向申请人支付加班工资差额人民币 {ot_info['amount']:.2f} 元",
                "short_title": ot_info["claim_title"],
                "category": "labor_remuneration",
                "amount": ot_info["amount"],
                "formula": ot_info["formula"],
                "legal_basis": ot_info["legal_basis"],
            }
        )

    finality_report = classify_article_47_finality(claim_items, min_wage)
    grand_total = money(sum((to_dec(c["amount"]) for c in claim_items), Decimal("0.00")))

    # Mediation discount tiers (A: 90%, B: 75%, C: 65%)
    mediation_tiers = {
        "tier_A_optimal": float(money(grand_total * Decimal("0.90"))),
        "tier_B_pragmatic": float(money(grand_total * Decimal("0.75"))),
        "tier_C_floor": float(money(grand_total * Decimal("0.65"))),
    }

    return {
        "city": city,
        "benchmarks": {
            "soc_avg_monthly": float(soc_avg),
            "soc_avg_3x_cap": float(money(soc_avg * Decimal("3"))),
            "min_wage_monthly": float(min_wage),
            "article_47_finality_threshold": float(money(min_wage * Decimal("12"))),
            "region_note": bench["region_note"],
        },
        "tenure": tenure,
        "wage": wage_info,
        "termination": term_info,
        "double_wage": double_wage_info,
        "annual_leave": leave_info,
        "overtime": ot_info,
        "article_47_finality": finality_report,
        "grand_total": float(grand_total),
        "mediation_tiers": mediation_tiers,
        "warnings": term_info["warnings"],
        "statutory_conflicts": term_info["statutory_conflicts"],
    }


def format_markdown_report(result: dict[str, Any]) -> str:
    """Format calculation result into a clean Markdown legal calculation schedule."""
    lines = [
        f"# 劳动人事争议仲裁请求金额精算表（管辖基准：{result['city']}）",
        "",
        "## 一、 核算基准参数",
        f"- **入职至离职周期**：`{result['tenure']['start_date']}` 至 `{result['tenure']['end_date']}`（共 `{result['tenure']['total_calendar_days']}` 天）",
        f"- **法定工作年限折算**：{result['tenure']['tenure_description']}",
        f"- **离职前 12 个月平均应得工资（税前应发）**：`¥{result['wage']['effective_avg_wage']:,.2f}` 元/月",
        f"- **当地社平工资 3 倍封顶线**：`¥{result['benchmarks']['soc_avg_3x_cap']:,.2f}` 元/月（月最低工资：`¥{result['benchmarks']['min_wage_monthly']:,.2f}` 元）",
        f"- **《调解仲裁法》第 47 条一裁终局单项阈值**：`¥{result['benchmarks']['article_47_finality_threshold']:,.2f}` 元（月最低工资 × 12）",
        "",
        "## 二、 分项仲裁请求核算明细表",
        "",
        "| 请求序号 | 仲裁请求事项 | 主张金额 (元) | 计算公式与过程 | 法定依据 | 第47条一裁终局属性 |",
        "| :---: | :--- | ---: | :--- | :--- | :--- |",
    ]
    for item in result["article_47_finality"]["claims"]:
        lines.append(
            f"| 请求 {item['index']} | {item['title']} | **{item['amount']:,.2f}** | {item['formula']} | {item['legal_basis']} | {item['finality_tag']} |"
        )
    lines.extend(
        [
            f"| **合计** | **以上各项仲裁请求金额总计** | **¥{result['grand_total']:,.2f}** | 分项独立列明，避免笼统合并 | — | {'全部符合一裁终局' if result['article_47_finality']['all_claims_final'] else '含非终局或超阈值项'} |",
            "",
            "## 三、 诉求拆分与调解底线建议",
            f"- **一裁终局策略评估**：{result['article_47_finality']['strategy_advice']}",
            f"- **庭前/庭审一次性现金调解参考方案**：",
            f"  - **A 档（理想目标，90% 折现）**：`¥{result['mediation_tiers']['tier_A_optimal']:,.2f}` 元（要求当庭或 7 日内一次性转账付清，附逾期双倍违约金条款）",
            f"  - **B 档（务实折中，75% 折现）**：`¥{result['mediation_tiers']['tier_B_pragmatic']:,.2f}` 元（免除一审二审 6~9 个月时间成本）",
            f"  - **C 档（谈判底线，65% 折现）**：`¥{result['mediation_tiers']['tier_C_floor']:,.2f}` 元",
        ]
    )
    if result["statutory_conflicts"] or result["warnings"]:
        lines.append("")
        lines.append("## 四、 合规审查与风险提示")
        for c in result["statutory_conflicts"]:
            lines.append(f"- {c}")
        for w in result["warnings"]:
            lines.append(f"- {w}")
    return "\n".join(lines) + "\n"


def parse_profile_markdown(profile_path: Path) -> dict[str, Any]:
    """Extract JSON block or key-value fields from `01-case-profile.md`."""
    text = profile_path.read_text(encoding="utf-8")
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    raise ValueError(f"Could not find an embedded ```json ... ``` calculation block in {profile_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic China Labor Arbitration Calculator")
    parser.add_argument("--input", type=Path, help="Path to JSON input file")
    parser.add_argument("--profile", type=Path, help="Path to 01-case-profile.md containing embedded JSON block")
    parser.add_argument("--city", default="深圳", help="Jurisdiction city name (e.g. 北京, 上海, 深圳, 广州, 杭州, 成都)")
    parser.add_argument("--start-date", help="Employment start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="Employment termination date (YYYY-MM-DD)")
    parser.add_argument("--avg-wage", type=float, help="12-month pre-termination average gross monthly wage")
    parser.add_argument("--last-month-wage", type=float, help="Last full month gross wage (used for +1 notice pay)")
    parser.add_argument("--mode", default="2N", choices=["2N", "N", "N+1", "FORCED_N", "CONTINUE", "NONE"], help="Termination claim mode")
    parser.add_argument("--unwritten-months", type=float, default=0.0, help="Unwritten contract months (max 11)")
    parser.add_argument("--untaken-leave-days", type=float, default=None, help="Untaken paid annual leave days")
    parser.add_argument("--unpaid-wages", type=float, default=0.0, help="Unpaid salary arrears amount")
    parser.add_argument("--overtime-weekday", type=float, default=0.0, help="Weekday overtime hours (150%%)")
    parser.add_argument("--overtime-weekend", type=float, default=0.0, help="Weekend overtime hours (200%%)")
    parser.add_argument("--overtime-holiday", type=float, default=0.0, help="Statutory holiday overtime hours (300%%)")
    parser.add_argument("--soc-avg", type=float, default=None, help="Override local social average monthly wage")
    parser.add_argument("--min-wage", type=float, default=None, help="Override local minimum monthly wage")
    parser.add_argument("--json", action="store_true", help="Print JSON output to stdout")
    parser.add_argument("--output", type=Path, help="Write JSON result to file")
    args = parser.parse_args(argv)

    if args.input:
        data = json.loads(args.input.read_text(encoding="utf-8"))
    elif args.profile:
        data = parse_profile_markdown(args.profile)
    else:
        if not args.start_date or not args.end_date or args.avg_wage is None:
            parser.error("Either --input, --profile, or (--start-date, --end-date, --avg-wage) must be provided.")
        data = {
            "city": args.city,
            "start_date": args.start_date,
            "end_date": args.end_date,
            "avg_wage": args.avg_wage,
            "last_month_wage": args.last_month_wage,
            "termination_mode": args.mode,
            "unwritten_contract_months": args.unwritten_months,
            "untaken_leave_days": args.untaken_leave_days,
            "unpaid_wages_amount": args.unpaid_wages,
            "overtime_weekday_hours": args.overtime_weekday,
            "overtime_weekend_hours": args.overtime_weekend,
            "overtime_holiday_hours": args.overtime_holiday,
            "soc_avg_monthly": args.soc_avg,
            "min_wage_monthly": args.min_wage,
        }

    result = calculate_case(data)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_markdown_report(result))

    return 0


if __name__ == "__main__":
    sys.exit(main())
