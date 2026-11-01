#!/usr/bin/env python3
"""Static Compliance, Arithmetic, and Layout Verifier for LaborShield Dockets.

Verifies both `draft.json` and the compiled `.docx` 6-pack in a docket directory:
1. Respondent 18-char Unified Social Credit Code (USCC) format check
2. Zero-drift arithmetic check across `draft.json`, `calc_result.json`, and `.docx` files
3. Statutory exclusivity conflict check (e.g. "Continue Contract" + "2N", or "2N" + "+1 Notice Pay")
4. Terminology & Evidence Purpose discipline check (rejects "原告/被告" in arbitration dockets
   and colloquial/emotional phrases in evidence purposes)
5. 18-Element table completeness check
6. Evidence catalog sequential numbering (1..N) and continuous page range (P1..PK) check
7. Compiled `.docx` 6-pack existence, XML integrity, and mandatory footer disclaimer check

Exit code 0 on pass, 1 with detailed failure list otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import docx

EXPECTED_FILES = [
    "01_劳动人事争议仲裁申请书_标准式.docx",
    "02_劳动人事争议仲裁要素表_要素式.docx",
    "03_仲裁请求金额核算明细表.docx",
    "04_申请人证据目录及证明目的清单.docx",
    "05_送达地址确认书及诚信仲裁承诺书.docx",
    "06_程序性附件_法定代表人证明及授权委托书模板.docx",
    "07_庭审举证质证与调解应对手册.md",
]

USCC_REGEX = re.compile(r"^[0-9A-HJ-NPQRTUWXY]{18}$")
PAGE_RANGE_REGEX = re.compile(r"^P?(\d+)(?:-P?(\d+))?$", re.IGNORECASE)

BANNED_LITIGATION_TERMS = ["原告", "被告"]
BANNED_COLLOQUIAL_PURPOSE_PHRASES = [
    "故意刁难",
    "说话不算数",
    "黑心老板",
    "无良公司",
    "欺负老实人",
    "穿小鞋",
    "恶心人",
]


def money(val: Any) -> Decimal:
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def extract_docx_text(docx_path: Path) -> str:
    """Extract all paragraph, table, and footer text from a .docx file."""
    doc = docx.Document(str(docx_path))
    chunks: list[str] = []
    for p in doc.paragraphs:
        if p.text:
            chunks.append(p.text)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text:
                    chunks.append(cell.text)
    for section in doc.sections:
        for p in section.footer.paragraphs:
            if p.text:
                chunks.append(p.text)
    return "\n".join(chunks)


def verify_docket_package(
    docket_dir: Path,
    calc_json_path: Path | None = None,
    draft_json_path: Path | None = None,
) -> list[str]:
    errors: list[str] = []

    d_path = draft_json_path or (docket_dir / "draft.json")
    if not d_path.is_file():
        errors.append(f"missing draft.json at {d_path}")
        return errors

    try:
        draft = json.loads(d_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"draft.json is not valid JSON: {exc}")
        return errors

    # 1. Applicant & Respondent identity checks
    app = draft.get("applicant", {})
    for key in ("name", "id_number", "address", "phone"):
        if not str(app.get(key, "")).strip():
            errors.append(f"applicant.{key} is missing or empty")

    resp_list = draft.get("respondents") if isinstance(draft.get("respondents"), list) else ([draft["respondent"]] if "respondent" in draft else [])
    if not resp_list:
        errors.append("no respondent found in draft.json")
    for idx, resp in enumerate(resp_list, start=1):
        uscc = str(resp.get("uscc", "")).strip()
        if not USCC_REGEX.match(uscc):
            errors.append(
                f"respondent[{idx}] ('{resp.get('name', '?')}'): invalid 18-character Unified Social Credit Code (USCC): {uscc!r}"
            )
        if not str(resp.get("name", "")).strip():
            errors.append(f"respondent[{idx}].name is empty")
        if not str(resp.get("address", "")).strip():
            errors.append(f"respondent[{idx}].address is empty")

    if not str(draft.get("jurisdiction_commission", "")).strip().endswith("仲裁委员会"):
        errors.append(
            f"jurisdiction_commission must end with '仲裁委员会' (found: {draft.get('jurisdiction_commission')!r})"
        )

    # 2. Claims continuity, arithmetic, and statutory exclusivity conflict checks
    claims = draft.get("claims", [])
    if not claims:
        errors.append("draft.json contains zero arbitration claims")

    claim_titles_joined = " | ".join(str(c.get("title", "")) + " " + str(c.get("short_title", "")) for c in claims)

    # Statutory conflict 1: Continue performing contract + Termination damages/severance
    if "继续履行劳动合同" in claim_titles_joined and any(
        kw in claim_titles_joined for kw in ("违法解除", "赔偿金", "经济补偿")
    ):
        errors.append(
            "statutory conflict: cannot simultaneously claim '继续履行劳动合同' and termination severance/damages ('经济补偿金/赔偿金')"
        )

    # Statutory conflict 2: Illegal termination (2N) or Forced termination (Art. 38) + Notice pay (+1)
    if ("违法解除" in claim_titles_joined or "被迫解除" in claim_titles_joined) and (
        "代通知金" in claim_titles_joined or "未提前三十日书面通知" in claim_titles_joined
    ):
        errors.append(
            "statutory conflict: cannot simultaneously claim '违法解除赔偿金(2N)/被迫解除补偿金(N)' and '未提前三十日书面通知代通知金(+1)'"
        )

    draft_total = Decimal("0.00")
    for expected_idx, item in enumerate(claims, start=1):
        if item.get("index") != expected_idx:
            errors.append(f"claims numbering discontinuity: expected index {expected_idx}, found {item.get('index')}")
        amt = money(item.get("amount", 0))
        if amt <= 0 and "继续履行" not in str(item.get("title", "")):
            errors.append(f"claim[{expected_idx}] amount must be > 0 (found {amt})")
        draft_total += amt

    # Cross-check against calc_result.json if provided
    if calc_json_path and calc_json_path.is_file():
        calc_data = json.loads(calc_json_path.read_text(encoding="utf-8"))
        calc_total = money(calc_data.get("grand_total", 0))
        if draft_total != calc_total:
            errors.append(
                f"arithmetic mismatch: sum of claims in draft.json ({draft_total:.2f}) != calc_result.json grand_total ({calc_total:.2f})"
            )
        calc_claims = calc_data.get("article_47_finality", {}).get("claims", [])
        if len(claims) != len(calc_claims):
            errors.append(
                f"claim count mismatch: draft.json has {len(claims)} claims, calc_result.json has {len(calc_claims)} claims"
            )
        else:
            for c_draft, c_calc in zip(claims, calc_claims):
                if money(c_draft["amount"]) != money(c_calc["amount"]):
                    errors.append(
                        f"claim[{c_draft.get('index')}] amount mismatch: draft={money(c_draft['amount']):.2f} vs calc={money(c_calc['amount']):.2f}"
                    )

    # 3. 18-Element table check
    elements = draft.get("elements_18", [])
    if len(elements) != 18:
        errors.append(f"elements_18 must contain exactly 18 standard arbitration elements (found {len(elements)})")
    for idx, elem in enumerate(elements, start=1):
        if elem.get("index") != idx:
            errors.append(f"elements_18 index mismatch at position {idx}: found {elem.get('index')}")
        if not str(elem.get("value", "")).strip():
            errors.append(f"elements_18[{idx}] ('{elem.get('label', '?')}') value is empty")

    # 4. Evidence catalog continuity, page ranges, and purpose discipline
    ev_list = draft.get("evidence_catalog", [])
    if not ev_list:
        errors.append("evidence_catalog is empty")

    expected_next_page = 1
    for expected_idx, ev in enumerate(ev_list, start=1):
        if ev.get("index") != expected_idx:
            errors.append(f"evidence_catalog index discontinuity: expected {expected_idx}, found {ev.get('index')}")
        purpose = str(ev.get("purpose", "")).strip()
        if not purpose.startswith("证明"):
            errors.append(
                f"evidence[{expected_idx}] ('{ev.get('name', '?')}'): purpose must start with standard judicial phrasing '证明...' (found: {purpose[:30]!r})"
            )
        for bad_phrase in BANNED_COLLOQUIAL_PURPOSE_PHRASES:
            if bad_phrase in purpose:
                errors.append(
                    f"evidence[{expected_idx}] purpose contains banned emotional/colloquial phrase {bad_phrase!r}: {purpose!r}"
                )

        pr = str(ev.get("page_range", "")).strip()
        m = PAGE_RANGE_REGEX.match(pr)
        if not m:
            errors.append(
                f"evidence[{expected_idx}] invalid page_range format {pr!r} (expected e.g. 'P1-P3' or 'P4')"
            )
        else:
            p_start = int(m.group(1))
            p_end = int(m.group(2)) if m.group(2) else p_start
            if p_end < p_start:
                errors.append(f"evidence[{expected_idx}] page_range end ({p_end}) < start ({p_start}) in {pr!r}")
            if p_start != expected_next_page:
                errors.append(
                    f"evidence[{expected_idx}] page_range discontinuity: expected start page P{expected_next_page}, found P{p_start} ({pr!r})"
                )
            expected_next_page = p_end + 1

    # 5. Terminology check in facts_and_reasons
    facts_text = "\n".join(str(p) for p in draft.get("facts_and_reasons", []))
    for bad_term in BANNED_LITIGATION_TERMS:
        if bad_term in facts_text:
            errors.append(
                f"facts_and_reasons contains civil litigation term {bad_term!r}; labor arbitration must strictly use '申请人' and '被申请人'"
            )

    # 6. Verify compiled .docx and .md files on disk
    for fname in EXPECTED_FILES:
        fpath = docket_dir / fname
        if not fpath.is_file():
            errors.append(f"missing deliverable file: {fpath}")
            continue
        if fname.endswith(".docx"):
            try:
                text = extract_docx_text(fpath)
            except Exception as exc:
                errors.append(f"failed to read/parse docx file {fname}: {exc}")
                continue
            if "【重要合规声明】" not in text:
                errors.append(f"{fname}: missing mandatory legal compliance disclaimer in footer/body")
            if fname.startswith("01_") or fname.startswith("03_"):
                if f"{draft_total:.2f}" not in text:
                    errors.append(f"{fname}: total claim amount '{draft_total:.2f}' not found in rendered document")
            if fname.startswith("01_"):
                for bad_term in BANNED_LITIGATION_TERMS:
                    if bad_term in text:
                        errors.append(f"{fname}: contains forbidden litigation term {bad_term!r}")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify LaborShield Docket Package")
    parser.add_argument("docket_dir", type=Path, help="Directory containing draft.json and generated .docx files")
    parser.add_argument("--calc", type=Path, default=None, help="Optional calc_result.json to verify zero arithmetic drift")
    parser.add_argument("--draft", type=Path, default=None, help="Optional explicit path to draft.json")
    args = parser.parse_args(argv)

    errors = verify_docket_package(args.docket_dir, calc_json_path=args.calc, draft_json_path=args.draft)
    if errors:
        print(f"verify_docket: FAILED ({len(errors)} error(s))")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"verify_docket: PASS (all 7 statutory, arithmetic, and .docx layout checks succeeded for {args.docket_dir})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
