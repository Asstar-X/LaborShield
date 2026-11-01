"""Unit tests for tools/generate_docket_docx.py."""

from __future__ import annotations

from pathlib import Path

from tools.generate_docket_docx import generate_all_dockets
from tools.verify_docket import EXPECTED_FILES, extract_docx_text


def test_generate_all_dockets_creates_7_deliverables(tmp_path: Path) -> None:
    fixture_draft = Path(__file__).resolve().parent / "fixtures" / "sample_case_draft.json"
    created = generate_all_dockets(fixture_draft, output_dir=tmp_path)
    assert len(created) == 7

    for expected_name in EXPECTED_FILES:
        f = tmp_path / expected_name
        assert f.is_file(), f"Expected deliverable {expected_name} was not created"

    app_text = extract_docx_text(tmp_path / "01_劳动人事争议仲裁申请书_标准式.docx")
    assert "林远航" in app_text
    assert "深圳市星云智联科技有限公司" in app_text
    assert "91440300MA5FX8892K" in app_text
    assert "145862.07" in app_text
    assert "【重要合规声明】" in app_text
