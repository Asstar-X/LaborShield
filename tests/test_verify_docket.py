"""Unit tests for tools/verify_docket.py static compliance checks."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from tools.generate_docket_docx import generate_all_dockets
from tools.verify_docket import verify_docket_package


def _load_fixture_draft() -> dict:
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "sample_case_draft.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_verify_valid_docket_passes(tmp_path: Path) -> None:
    draft = _load_fixture_draft()
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    generate_all_dockets(draft_path, output_dir=tmp_path)

    errors = verify_docket_package(tmp_path)
    assert errors == []


def test_verify_catches_invalid_uscc_and_statutory_conflicts(tmp_path: Path) -> None:
    draft = _load_fixture_draft()
    draft["respondents"][0]["uscc"] = "INVALID_USCC_123"
    # Inject statutory conflict: Continue contract + 2N damages, and 2N + Notice Pay (+1)
    draft["claims"].append(
        {
            "index": 5,
            "title": "请求裁决继续履行劳动合同并支付未提前三十日书面通知代通知金 18000.00 元",
            "short_title": "继续履行劳动合同及代通知金",
            "category": "severance_or_damages",
            "amount": 18000.0,
            "formula": "18000",
            "legal_basis": "第40条",
            "is_article_47_final": True,
        }
    )
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    generate_all_dockets(draft_path, output_dir=tmp_path)

    errors = verify_docket_package(tmp_path)
    joined = "\n".join(errors)
    assert "Unified Social Credit Code" in joined
    assert "statutory conflict: cannot simultaneously claim '继续履行劳动合同'" in joined
    assert "statutory conflict: cannot simultaneously claim '违法解除赔偿金(2N)" in joined


def test_verify_catches_forbidden_litigation_terms_and_page_gaps(tmp_path: Path) -> None:
    draft = copy.deepcopy(_load_fixture_draft())
    draft["facts_and_reasons"][0] = "原告于2021年入职被告公司工作。"
    draft["evidence_catalog"][0]["purpose"] = "这个证明老板故意刁难我、说话不算数"
    draft["evidence_catalog"][1]["page_range"] = "P5-P10"  # Gap: P3-P4 missing after P1-P2

    draft_path = tmp_path / "draft.json"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    generate_all_dockets(draft_path, output_dir=tmp_path)

    errors = verify_docket_package(tmp_path)
    joined = "\n".join(errors)
    assert "原告" in joined
    assert "故意刁难" in joined
    assert "purpose must start with standard judicial phrasing '证明...'" in joined
    assert "page_range discontinuity: expected start page P3, found P5" in joined
