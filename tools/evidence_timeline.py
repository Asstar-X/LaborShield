#!/usr/bin/env python3
"""Evidence Timeline Reconstruction, Page Numbering, and Electronic Data Audit Tool.

Scans `evidence/` subfolders or a JSON manifest, extracts timestamps (YYYY-MM-DD),
assigns continuous judicial page ranges (P1-P...), and audits electronic evidence
against PRC Civil Procedure Evidence Rules (WeChat identity page check & audio
transcript check).

Usage:
  python3 tools/evidence_timeline.py --evidence-dir evidence --json
  python3 tools/evidence_timeline.py --manifest evidence_manifest.json --output page_assigned.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

EVIDENCE_CATEGORIES = [
    ("01_identity_registration", "主体资格与工商登记证据组", "证明申请人与被申请人诉讼主体适格"),
    ("02_contracts_rules", "劳动关系建立与合同履行证据组", "证明双方依法建立劳动关系、约定工作岗位及薪酬标准"),
    ("03_salary_social_security", "薪资发放、个税与社保缴纳证据组", "证明申请人离职前12个月应得工资标准、实发工资及社保缴纳事实"),
    ("04_attendance_overtime", "考勤打卡、加班与年休假证据组", "证明申请人实际出勤、加班事实及未休带薪年休假情况"),
    ("05_termination_notices", "解除/终止劳动关系核心事实证据组", "证明被申请人违法解除劳动合同（或申请人被迫解除劳动合同）之事实"),
    ("06_communications_recordings", "沟通记录与视听资料补强证据组", "证明双方就争议事项沟通经过及被申请人相关自认事实"),
]

DATE_PATTERN = re.compile(r"(20\d{2})[-._年]?(0[1-9]|1[0-2])[-._月]?(0[1-9]|[12]\d|3[01])")
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"}


def extract_date_from_name(name: str) -> str | None:
    m = DATE_PATTERN.search(name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def assign_continuous_pages(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign continuous judicial page ranges `P1-P...` and sequential index `1..N`."""
    current_page = 1
    output: list[dict[str, Any]] = []
    for idx, item in enumerate(items, start=1):
        pages = max(1, int(item.get("page_count", 1)))
        start_p = current_page
        end_p = current_page + pages - 1
        page_range = f"P{start_p}" if start_p == end_p else f"P{start_p}-P{end_p}"
        current_page = end_p + 1
        updated = dict(item)
        updated["index"] = idx
        updated["page_count"] = pages
        updated["page_range"] = page_range
        output.append(updated)
    return output


def scan_evidence_directory(evidence_dir: Path) -> dict[str, Any]:
    """Scan `evidence/` subdirectories, build timeline, and detect 3-link electronic data gaps."""
    discovered: list[dict[str, Any]] = []
    warnings: list[str] = []

    has_wechat_chat = False
    has_wechat_identity = False
    audio_files: list[str] = []
    transcript_files: list[str] = []

    for folder_name, group_title, default_purpose in EVIDENCE_CATEGORIES:
        sub = evidence_dir / folder_name
        if not sub.is_dir():
            continue
        for fpath in sorted(sub.iterdir()):
            if fpath.name.startswith(".") or fpath.name.lower() == "readme.md":
                continue
            if fpath.is_file():
                dt = extract_date_from_name(fpath.name)
                fname_lower = fpath.name.lower()
                if any(k in fname_lower for k in ("微信", "wechat", "聊天", "钉钉", "飞书")):
                    if any(k in fname_lower for k in ("主页", "实名", "个人信息", "名片", "架构", "转账")):
                        has_wechat_identity = True
                    else:
                        has_wechat_chat = True
                if fpath.suffix.lower() in AUDIO_EXTENSIONS:
                    audio_files.append(fpath.name)
                if any(k in fname_lower for k in ("录音整理", "文字稿", "逐字稿", "transcript")):
                    transcript_files.append(fpath.name)

                discovered.append(
                    {
                        "category": folder_name,
                        "group_title": group_title,
                        "file_name": fpath.name,
                        "name": fpath.stem,
                        "date": dt or "未标注日期",
                        "source_and_form": "电子数据打印件/复印件（原件备查）",
                        "purpose": default_purpose,
                        "page_count": 1,
                    }
                )

    if has_wechat_chat and not has_wechat_identity:
        warnings.append(
            "【黄灯预警 - 电子数据主体缺失】检测到微信/钉钉聊天记录，但未发现对方账号“个人信息主页/实名认证/企业组织架构截图”。"
            "请务必补截对方微信号主页或实名转账校验页，形成“主体同一性+完整对话+原始载体”三连闭环。"
        )
    if audio_files and not transcript_files:
        warnings.append(
            f"【黄灯预警 - 录音缺少文字整理稿】检测到音频证据 {audio_files}，但未配备《录音文字整理稿》。"
            "仲裁庭通常拒收纯音频，必须整理逐字稿并在关键争议事实处标明 [MM:SS] 秒级时间戳。"
        )

    catalog = assign_continuous_pages(discovered)
    timeline = sorted(
        [item for item in catalog if item["date"] != "未标注日期"],
        key=lambda x: x["date"],
    )

    return {
        "total_evidence_items": len(catalog),
        "total_pages": sum(item["page_count"] for item in catalog),
        "evidence_catalog": catalog,
        "chronological_timeline": timeline,
        "audit_warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evidence Timeline and Continuous Page Numbering Tool")
    parser.add_argument("--evidence-dir", type=Path, default=Path("evidence"), help="Path to evidence directory")
    parser.add_argument("--manifest", type=Path, default=None, help="JSON list of evidence items to number")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument("--output", type=Path, default=None, help="Write JSON result to file")
    args = parser.parse_args(argv)

    if args.manifest:
        raw_items = json.loads(args.manifest.read_text(encoding="utf-8"))
        numbered = assign_continuous_pages(raw_items)
        result = {
            "total_evidence_items": len(numbered),
            "total_pages": sum(i["page_count"] for i in numbered),
            "evidence_catalog": numbered,
            "chronological_timeline": sorted(
                [i for i in numbered if i.get("date") and i.get("date") != "未标注日期"],
                key=lambda x: str(x["date"]),
            ),
            "audit_warnings": [],
        }
    else:
        result = scan_evidence_directory(args.evidence_dir)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"# 证据目录与时间轴盘点（共 {result['total_evidence_items']} 项，合计 {result['total_pages']} 页）\n")
        for item in result["evidence_catalog"]:
            print(f"- **证据{item['index']}** [{item['page_range']}]：{item['name']}（{item['source_and_form']}） → {item['purpose']}")
        if result["audit_warnings"]:
            print("\n## 电子证据三性合规预警")
            for w in result["audit_warnings"]:
                print(f"- {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
