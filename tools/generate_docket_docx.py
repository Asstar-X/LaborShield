#!/usr/bin/env python3
"""Generate Standardized Chinese Labor Arbitration Docket Package (.docx 6-Pack + Hearing Card).

Renders structured `draft.json` (and `calc_result.json`) into 6 official judicial-grade
Word (.docx) documents and 1 internal hearing playbook (.md):
  01_劳动人事争议仲裁申请书_标准式.docx
  02_劳动人事争议仲裁要素表_要素式.docx
  03_仲裁请求金额核算明细表.docx
  04_申请人证据目录及证明目的清单.docx
  05_送达地址确认书及诚信仲裁承诺书.docx
  06_程序性附件_法定代表人证明及授权委托书模板.docx
  07_庭审举证质证与调解应对手册.md

Usage:
  python3 tools/generate_docket_docx.py dockets/case_001/draft.json --output-dir dockets/case_001
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import docx
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor

MANDATORY_DISCLAIMER = (
    "【重要合规声明】本文件由本地数字化效率工具（LaborShield）辅助排版整理，"
    "不提供任何形式的执业法律咨询或诉讼代理服务，不构成正式法律意见。"
    "递交前请申请人本人逐字核对全部事实、金额与证据原件；如遇重大疑难争议，请咨询执业律师或致电12348法律援助热线。"
)

COLOR_BLACK = RGBColor(0, 0, 0)
COLOR_DARK_GRAY = RGBColor(35, 35, 35)
COLOR_MUTED = RGBColor(105, 105, 105)
HEX_HEADER_BG = "F2F4F4"


def setup_judicial_page(doc: docx.Document) -> None:
    """Configure A4 portrait layout with Chinese judicial binding margins and footer disclaimer."""
    for section in doc.sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.2)
        section.left_margin = Cm(2.8)
        section.right_margin = Cm(2.2)

        footer = section.footer
        p_foot = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        p_foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p_foot.add_run(MANDATORY_DISCLAIMER)
        set_run_font(run, "宋体", 8.0, bold=False, color=COLOR_MUTED)

    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(14)
    style.font.color.rgb = COLOR_BLACK
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "仿宋_GB2312")


def set_run_font(
    run: Any,
    cn_font: str = "仿宋_GB2312",
    size_pt: float = 14.0,
    bold: bool = False,
    color: RGBColor = COLOR_BLACK,
) -> None:
    run.font.name = "Times New Roman"
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.color.rgb = color
    run._element.rPr.rFonts.set(qn("w:eastAsia"), cn_font)


def add_title(doc: docx.Document, text: str, subtitle: str | None = None) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(10 if not subtitle else 4)
    p.paragraph_format.line_spacing = Pt(28)
    r = p.add_run(text)
    set_run_font(r, "黑体", 20.0, bold=True)

    if subtitle:
        p_sub = doc.add_paragraph()
        p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_sub.paragraph_format.space_before = Pt(0)
        p_sub.paragraph_format.space_after = Pt(10)
        r_sub = p_sub.add_run(subtitle)
        set_run_font(r_sub, "仿宋_GB2312", 12.0, bold=False, color=COLOR_DARK_GRAY)


def add_heading_1(doc: docx.Document, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = Pt(26)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    set_run_font(r, "黑体", 15.0, bold=True)


def add_body_paragraph(
    doc: docx.Document,
    text: str,
    indent_first_line: bool = True,
    bold_prefix: str | None = None,
    size_pt: float = 14.0,
) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = Pt(26)
    if indent_first_line:
        p.paragraph_format.first_line_indent = Pt(size_pt * 2)

    if bold_prefix:
        r_pre = p.add_run(bold_prefix)
        set_run_font(r_pre, "黑体", size_pt, bold=True)
    r = p.add_run(text)
    set_run_font(r, "仿宋_GB2312", size_pt, bold=False)


def set_cell_margins(cell: Any, top: int = 80, bottom: int = 80, left: int = 120, right: int = 120) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement("w:tcMar")
    for margin_name, val in [("top", top), ("bottom", bottom), ("left", left), ("right", right)]:
        node = OxmlElement(f"w:{margin_name}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        tcMar.append(node)
    tcPr.append(tcMar)


def set_cell_shading(cell: Any, hex_color: str) -> None:
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading)


def style_judicial_table(table: Any, col_widths_cm: list[float]) -> None:
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        '<w:top w:val="single" w:sz="6" w:space="0" w:color="000000"/>'
        '<w:left w:val="single" w:sz="6" w:space="0" w:color="000000"/>'
        '<w:bottom w:val="single" w:sz="6" w:space="0" w:color="000000"/>'
        '<w:right w:val="single" w:sz="6" w:space="0" w:color="000000"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        "</w:tblBorders>"
    )
    tblPr.append(borders)

    for row_idx, row in enumerate(table.rows):
        trPr = row._tr.get_or_add_trPr()
        trPr.append(OxmlElement("w:cantSplit"))
        if row_idx == 0:
            trPr.append(OxmlElement("w:tblHeader"))
        for col_idx, cell in enumerate(row.cells):
            if col_idx < len(col_widths_cm):
                cell.width = Cm(col_widths_cm[col_idx])
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            set_cell_margins(cell)


def fill_cell(
    cell: Any,
    text: str,
    bold: bool = False,
    align: Any = WD_ALIGN_PARAGRAPH.LEFT,
    size_pt: float = 11.0,
    cn_font: str = "宋体",
) -> None:
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.line_spacing = Pt(16)
    r = p.add_run(str(text))
    set_run_font(r, cn_font, size_pt, bold=bold)


def render_01_standard_application(draft: dict[str, Any], out_dir: Path) -> Path:
    """01_劳动人事争议仲裁申请书_标准式.docx"""
    doc = docx.Document()
    setup_judicial_page(doc)
    add_title(doc, "劳动人事争议仲裁申请书")

    app = draft["applicant"]
    resp_list = draft["respondents"] if isinstance(draft.get("respondents"), list) else [draft["respondent"]]

    add_body_paragraph(
        doc,
        f"{app['name']}，性别：{app.get('gender', '—')}，民族：{app.get('ethnicity', '汉族')}，"
        f"出生日期：{app.get('birth_date', '—')}，公民身份号码：{app['id_number']}，"
        f"住址：{app['address']}，联系电话：{app['phone']}。",
        indent_first_line=False,
        bold_prefix="申请人：",
    )

    for idx, resp in enumerate(resp_list, start=1):
        prefix = "被申请人：" if len(resp_list) == 1 else f"第{idx}被申请人："
        add_body_paragraph(
            doc,
            f"{resp['name']}，统一社会信用代码：{resp['uscc']}，"
            f"住所地：{resp['address']}，"
            f"法定代表人/主要负责人：{resp.get('legal_representative', '—')}（职务：{resp.get('rep_title', '法定代表人')}），"
            f"联系电话：{resp.get('phone', '—')}。",
            indent_first_line=False,
            bold_prefix=prefix,
        )

    add_heading_1(doc, "一、 仲裁请求")
    claims = draft["claims"]
    total_amount = 0.0
    for item in claims:
        amt = float(item.get("amount", 0.0))
        total_amount += amt
        final_note = "（属《劳动争议调解仲裁法》第四十七条一裁终局请求项）" if item.get("is_article_47_final") else ""
        add_body_paragraph(
            doc,
            f"{item['title']}{final_note}；",
            indent_first_line=True,
            bold_prefix=f"请求{item['index']}：",
        )
    add_body_paragraph(
        doc,
        f"以上各项仲裁请求标的额共计人民币 {total_amount:.2f} 元（详见附件《仲裁请求金额核算明细表》）。",
        indent_first_line=True,
        bold_prefix="请求金额合计：",
    )

    add_heading_1(doc, "二、 事实与理由")
    for para in draft["facts_and_reasons"]:
        add_body_paragraph(doc, para, indent_first_line=True)

    if draft.get("burden_of_proof_request"):
        add_heading_1(doc, "三、 责令被申请人限期提供证据申请（举证责任倒置）")
        add_body_paragraph(doc, draft["burden_of_proof_request"], indent_first_line=True)

    add_body_paragraph(doc, "综上所述，为维护申请人的合法劳动权益，特依据《中华人民共和国劳动争议调解仲裁法》《中华人民共和国劳动合同法》之规定，向贵委申请仲裁，恳请依法裁决支持申请人的全部仲裁请求！", indent_first_line=True)

    add_body_paragraph(doc, "此致", indent_first_line=True)
    add_body_paragraph(doc, f"{draft['jurisdiction_commission']}", indent_first_line=False, bold_prefix="")

    p_sig = doc.add_paragraph()
    p_sig.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_sig.paragraph_format.space_before = Pt(18)
    r_sig = p_sig.add_run(f"申请人（签名/捺印）：{app['name']}\n申请日期：{draft.get('filing_date', '____年__月__日')}")
    set_run_font(r_sig, "仿宋_GB2312", 14.0, bold=False)

    p_notice = doc.add_paragraph()
    p_notice.paragraph_format.space_before = Pt(12)
    r_notice = p_notice.add_run(MANDATORY_DISCLAIMER)
    set_run_font(r_notice, "宋体", 8.5, bold=False, color=COLOR_MUTED)

    path = out_dir / "01_劳动人事争议仲裁申请书_标准式.docx"
    doc.save(str(path))
    return path


def render_02_element_table(draft: dict[str, Any], out_dir: Path) -> Path:
    """02_劳动人事争议仲裁要素表_要素式.docx (18 Standard Elements)"""
    doc = docx.Document()
    setup_judicial_page(doc)
    add_title(doc, "劳动人事争议仲裁要素表", subtitle=f"（适用管辖：{draft['jurisdiction_commission']}）")

    elements = draft["elements_18"]
    table = doc.add_table(rows=1 + len(elements), cols=3)
    headers = ["要素序号", "审理核心要素项目", "申请人填写内容（核定事实与依据）"]
    for c_idx, h_text in enumerate(headers):
        cell = table.cell(0, c_idx)
        set_cell_shading(cell, HEX_HEADER_BG)
        fill_cell(cell, h_text, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size_pt=11.0, cn_font="黑体")

    for r_idx, elem in enumerate(elements, start=1):
        fill_cell(table.cell(r_idx, 0), str(elem["index"]), bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size_pt=10.5)
        fill_cell(table.cell(r_idx, 1), elem["label"], bold=True, align=WD_ALIGN_PARAGRAPH.LEFT, size_pt=10.5)
        fill_cell(table.cell(r_idx, 2), elem["value"], bold=False, align=WD_ALIGN_PARAGRAPH.LEFT, size_pt=10.5)

    style_judicial_table(table, [2.0, 4.8, 9.2])

    add_body_paragraph(
        doc,
        "申请人确认：以上要素表填写内容真实、准确，与《劳动人事争议仲裁申请书》及所附证据材料一致。",
        indent_first_line=False,
        size_pt=11.0,
    )
    p_sig = doc.add_paragraph()
    p_sig.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_sig = p_sig.add_run(f"申请人签名：{draft['applicant']['name']}    日期：{draft.get('filing_date', '____年__月__日')}")
    set_run_font(r_sig, "仿宋_GB2312", 12.0)

    path = out_dir / "02_劳动人事争议仲裁要素表_要素式.docx"
    doc.save(str(path))
    return path


def render_03_calculation_sheet(draft: dict[str, Any], out_dir: Path) -> Path:
    """03_仲裁请求金额核算明细表.docx"""
    doc = docx.Document()
    setup_judicial_page(doc)
    add_title(doc, "仲裁请求金额核算明细表", subtitle="（作为《劳动人事争议仲裁申请书》之附件一并提交）")

    calc_meta = draft.get("calculation_summary", {})
    add_body_paragraph(
        doc,
        f"1. 入职与离职日期：{calc_meta.get('start_date', '—')} 至 {calc_meta.get('end_date', '—')}（{calc_meta.get('tenure_description', '—')}）；\n"
        f"2. 离职前12个月月平均应得工资（税前应发）：人民币 {float(calc_meta.get('effective_avg_wage', 0.0)):.2f} 元/月；\n"
        f"3. 当地社平工资3倍封顶基准：人民币 {float(calc_meta.get('soc_avg_3x_cap', 0.0)):.2f} 元/月；"
        f"《调解仲裁法》第四十七条一裁终局单项阈值（12个月最低工资）：人民币 {float(calc_meta.get('article_47_threshold', 0.0)):.2f} 元。",
        indent_first_line=False,
        bold_prefix="一、 核心核算基准参数：\n",
        size_pt=11.5,
    )

    claims = draft["claims"]
    table = doc.add_table(rows=2 + len(claims), cols=6)
    headers = ["序号", "请求项目", "主张金额(元)", "计算公式与核算过程", "法定依据", "第47条一裁终局属性"]
    for c_idx, h_text in enumerate(headers):
        cell = table.cell(0, c_idx)
        set_cell_shading(cell, HEX_HEADER_BG)
        fill_cell(cell, h_text, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size_pt=10.5, cn_font="黑体")

    total_amt = 0.0
    for idx, item in enumerate(claims, start=1):
        amt = float(item["amount"])
        total_amt += amt
        fill_cell(table.cell(idx, 0), f"请求{item['index']}", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size_pt=10.0)
        fill_cell(table.cell(idx, 1), item.get("short_title", item["title"]), bold=True, size_pt=10.0)
        fill_cell(table.cell(idx, 2), f"{amt:.2f}", bold=True, align=WD_ALIGN_PARAGRAPH.RIGHT, size_pt=10.0)
        fill_cell(table.cell(idx, 3), item["formula"], size_pt=9.5)
        fill_cell(table.cell(idx, 4), item["legal_basis"], size_pt=9.5)
        fill_cell(
            table.cell(idx, 5),
            "一裁终局项" if item.get("is_article_47_final") else "非终局项",
            align=WD_ALIGN_PARAGRAPH.CENTER,
            size_pt=9.5,
        )

    last_row = len(claims) + 1
    fill_cell(table.cell(last_row, 0), "合计", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size_pt=10.5)
    fill_cell(table.cell(last_row, 1), "全部仲裁请求金额总计", bold=True, size_pt=10.5)
    fill_cell(table.cell(last_row, 2), f"{total_amt:.2f}", bold=True, align=WD_ALIGN_PARAGRAPH.RIGHT, size_pt=10.5)
    fill_cell(table.cell(last_row, 3), "各分项独立核算汇总（详见上述分项公式）", size_pt=9.5)
    fill_cell(table.cell(last_row, 4), "《劳动争议调解仲裁法》第47条", size_pt=9.5)
    fill_cell(table.cell(last_row, 5), "分项独立审查", align=WD_ALIGN_PARAGRAPH.CENTER, size_pt=9.5)

    style_judicial_table(table, [1.4, 3.0, 2.3, 4.5, 3.0, 1.8])

    path = out_dir / "03_仲裁请求金额核算明细表.docx"
    doc.save(str(path))
    return path


def render_04_evidence_catalog(draft: dict[str, Any], out_dir: Path) -> Path:
    """04_申请人证据目录及证明目的清单.docx (Standard 5-Column Judicial Table)"""
    doc = docx.Document()
    setup_judicial_page(doc)
    add_title(doc, "申请人证据目录及证明目的清单", subtitle=f"（申请人：{draft['applicant']['name']}）")

    ev_list = draft["evidence_catalog"]
    table = doc.add_table(rows=1 + len(ev_list), cols=5)
    headers = ["证据序号", "证据名称", "证据来源与形式", "证明对象与证明目的", "页码范围"]
    for c_idx, h_text in enumerate(headers):
        cell = table.cell(0, c_idx)
        set_cell_shading(cell, HEX_HEADER_BG)
        fill_cell(cell, h_text, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size_pt=10.5, cn_font="黑体")

    for r_idx, ev in enumerate(ev_list, start=1):
        fill_cell(table.cell(r_idx, 0), f"证据{ev['index']}", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size_pt=10.5)
        fill_cell(table.cell(r_idx, 1), ev["name"], bold=True, size_pt=10.5)
        fill_cell(table.cell(r_idx, 2), ev["source_and_form"], align=WD_ALIGN_PARAGRAPH.CENTER, size_pt=10.0)
        fill_cell(table.cell(r_idx, 3), ev["purpose"], size_pt=10.0)
        fill_cell(table.cell(r_idx, 4), ev["page_range"], align=WD_ALIGN_PARAGRAPH.CENTER, size_pt=10.5)

    style_judicial_table(table, [1.8, 3.6, 2.6, 6.2, 1.8])

    add_body_paragraph(
        doc,
        "备注：以上证据复印件/打印件与原件（或原始电子载体）核对无异；开庭审理时申请人将携带全部书证原件及存有原始微信聊天记录、录音、个税App明细之移动终端当庭出示供核对。",
        indent_first_line=False,
        size_pt=10.5,
    )
    p_sig = doc.add_paragraph()
    p_sig.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_sig = p_sig.add_run(f"提交人（签名）：{draft['applicant']['name']}    提交日期：{draft.get('filing_date', '____年__月__日')}")
    set_run_font(r_sig, "仿宋_GB2312", 11.5)

    path = out_dir / "04_申请人证据目录及证明目的清单.docx"
    doc.save(str(path))
    return path


def render_05_service_address_confirmation(draft: dict[str, Any], out_dir: Path) -> Path:
    """05_送达地址确认书及诚信仲裁承诺书.docx"""
    doc = docx.Document()
    setup_judicial_page(doc)
    add_title(doc, "当事人送达地址确认书及诚信仲裁承诺书")

    app = draft["applicant"]
    rows_data = [
        ("案件当事人（申请人）", f"{app['name']}（公民身份号码：{app['id_number']}）"),
        ("确认线下邮寄送达地址", f"{app.get('service_address', app['address'])}（邮政编码：{app.get('postal_code', '000000')}）"),
        ("收件人及移动电话", f"收件人：{app['name']}    联系电话：{app['phone']}"),
        ("电子送达方式确认", f"同意接受短信、全国人社政务服务平台/地方仲裁微信小程序及电子邮箱（{app.get('email', '—')}）电子送达"),
        (
            "诚信仲裁与虚假陈述法律责任承诺",
            "本人承诺：向劳动人事争议仲裁委员会提交的仲裁申请书、要素表及全部证据材料均真实、合法，无伪造、变造证据或虚构劳动关系之行为；"
            "确认上述送达地址准确有效，若地址变更未及时书面告知仲裁委员会导致文书退回的，视为已合法送达。",
        ),
        ("当事人签名确认", f"签名（捺印）：{app['name']}          日期：{draft.get('filing_date', '____年__月__日')}"),
    ]

    table = doc.add_table(rows=len(rows_data), cols=2)
    for r_idx, (label, val) in enumerate(rows_data):
        cell_l = table.cell(r_idx, 0)
        set_cell_shading(cell_l, HEX_HEADER_BG)
        fill_cell(cell_l, label, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size_pt=11.0, cn_font="黑体")
        fill_cell(table.cell(r_idx, 1), val, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT, size_pt=11.0)

    style_judicial_table(table, [4.5, 11.5])
    path = out_dir / "05_送达地址确认书及诚信仲裁承诺书.docx"
    doc.save(str(path))
    return path


def render_06_procedural_attachments(draft: dict[str, Any], out_dir: Path) -> Path:
    """06_程序性附件_法定代表人证明及授权委托书模板.docx"""
    doc = docx.Document()
    setup_judicial_page(doc)
    resp_list = draft["respondents"] if isinstance(draft.get("respondents"), list) else [draft["respondent"]]
    resp = resp_list[0]
    app = draft["applicant"]

    add_title(doc, "被申请人法定代表人（主要负责人）身份证明书", subtitle="（供立案窗口核验被申请人工商公示负责人信息使用）")
    add_body_paragraph(
        doc,
        f"兹证明 {resp.get('legal_representative', '________')} 在被申请人 {resp['name']}（统一社会信用代码：{resp['uscc']}）"
        f"担任 {resp.get('rep_title', '法定代表人/执行董事')} 职务（数据来源：国家企业信用信息公示系统公示信息）。",
        indent_first_line=True,
    )
    add_body_paragraph(doc, f"特此证明。\n此致\n{draft['jurisdiction_commission']}", indent_first_line=True)

    add_heading_1(doc, "附：授权委托书（供申请人委托近亲属/法律援助人员/律师代理时备用）")
    add_body_paragraph(
        doc,
        f"委托人（申请人）：{app['name']}，公民身份号码：{app['id_number']}，电话：{app['phone']}。\n"
        "受委托人：____________，公民身份号码/执业证号：________________________，与委托人关系：____________。\n"
        f"现委托上述受委托人在委托人与 {resp['name']} 劳动人事争议仲裁一案中，作为委托人的仲裁代理人。\n"
        "代理权限为：【  】一般代理  / 【  】特别授权（代为提出、承认、放弃、变更仲裁请求，进行和解/调解，签署调解书，代收仲裁法律文书）。",
        indent_first_line=False,
        size_pt=12.0,
    )

    path = out_dir / "06_程序性附件_法定代表人证明及授权委托书模板.docx"
    doc.save(str(path))
    return path


def render_07_hearing_playbook(draft: dict[str, Any], out_dir: Path) -> Path:
    """07_庭审举证质证与调解应对手册.md (Internal Litigant Playbook)"""
    pb = draft.get("hearing_playbook", {})
    claims = draft["claims"]
    total = sum(float(c.get("amount", 0.0)) for c in claims)
    med = draft.get("mediation_tiers", {
        "tier_A_optimal": round(total * 0.90, 2),
        "tier_B_pragmatic": round(total * 0.75, 2),
        "tier_C_floor": round(total * 0.65, 2),
    })

    lines = [
        f"# 庭审举证质证与调解应对实战手册（申请人内部作战卡）",
        "",
        f"> **案由**：{draft['applicant']['name']} 诉 {draft['respondent']['name'] if 'respondent' in draft else draft['respondents'][0]['name']} 劳动人事争议案  ",
        f"> **管辖仲裁委**：{draft['jurisdiction_commission']}  ",
        f"> **警告**：本手册仅供申请人本人庭前演练与当庭应答参考，**严禁作为立案材料递交仲裁委或展示给被申请人**！",
        "",
        "---",
        "",
        "## 一、 仲裁员庭审调查必问核心问题标准应答卡",
        "",
    ]
    qa_list = pb.get("arbitrator_qa", [])
    if qa_list:
        for idx, qa in enumerate(qa_list, start=1):
            lines.append(f"### Q{idx}：{qa['question']}")
            lines.append(f"- **标准应答**：{qa['answer']}")
            lines.append("")
    else:
        for elem in draft["elements_18"][:8]:
            lines.append(f"- **{elem['label']}**：{elem['value']}")
        lines.append("")

    lines.extend([
        "## 二、 预判用人单位 HR 高频抗辩与“三性”质证反驳话术",
        "",
    ])
    for idx, defense in enumerate(pb.get("employer_defenses", []), start=1):
        claim_text = defense.get("claim") or defense.get("defense", "")
        lines.append(f"### 预判抗辩 {idx}：{claim_text}")
        lines.append(f"- **质证意见（真实性/合法性/关联性/证明目的）**：{defense['rebuttal']}")
        lines.append("")

    lines.extend([
        "## 三、 当庭申请责令被申请人提交证据口述词（举证责任倒置）",
        "",
        f"> “尊敬的仲裁员：依据《中华人民共和国劳动争议调解仲裁法》第六条、第三十九条及《最高人民法院关于审理劳动争议案件适用法律问题的解释（一）》第四十四条之规定，因用人单位作出解除劳动合同、减少劳动报酬、计算工作年限等决定发生的争议，由用人单位负举证责任；且考勤记录、工资发放台账由被申请人掌握管理。申请人已完成初步举证，现当庭申请责令被申请人限期提交原始考勤打卡记录及完整工资发放台账，若被申请人拒不提供，恳请依法推定申请人的主张成立！”",
        "",
        "## 四、 庭前/庭审调解三级现金折现底线方案",
        "",
        f"- **法定全额主张总额**：`¥{total:,.2f}` 元",
        f"- **A 档（理想调解方案 - 90%）**：`¥{float(med['tier_A_optimal']):,.2f}` 元 —— 要求当庭或 7 个自然日内一次性打入申请人银行账户，且调解书明确约定**“逾期未足额支付的，按原仲裁请求全额 ¥{total:,.2f} 元申请法院强制执行（或额外加付 30% 违约金）”**。",
        f"- **B 档（务实折中方案 - 75%）**：`¥{float(med['tier_B_pragmatic']):,.2f}` 元 —— 适合被申请人愿意在 10 日内一次性付清、免去后续一审二审 6~9 个月诉累的情形。",
        f"- **C 档（谈判绝对底线 - 65%）**：`¥{float(med['tier_C_floor']):,.2f}` 元 —— 低于此金额建议拒绝调解，坚持等待仲裁裁决（尤其针对符合第 47 条一裁终局之请求项）。",
        "",
        "## 五、 不服非终局裁决 15 日内转一审法院起诉操作指引",
        "",
        "1. **法定黄金 15 日红线**：自签收《仲裁裁决书》次日起算 **15 个自然日**内，若对非终局裁决不服，必须向用人单位所在地或劳动合同履行地**基层人民法院**提交一审起诉状（可通过“人民法院在线服务”微信小程序网上立案）。",
        "2. **2024 最高法要素式民事起诉状衔接**：本案生成的《02_劳动人事争议仲裁要素表》与最高人民法院、司法部、全国律协印发的《民事起诉状（劳动争议案件要素式示范文本）》字段 1:1 映射，仅需将“申请人/被申请人”替换为“原告/被告”，并补充“对 XX 劳人仲字〔202X〕第 XX 号仲裁裁决不服之具体事由”即可直接立案。",
        "",
        f"---\n{MANDATORY_DISCLAIMER}\n",
    ])

    path = out_dir / "07_庭审举证质证与调解应对手册.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def generate_all_dockets(draft_path: Path, output_dir: Path | None = None) -> list[Path]:
    """Generate the complete 6-docx + 1-md docket package from `draft.json`."""
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    out_dir = output_dir or draft_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    created = [
        render_01_standard_application(draft, out_dir),
        render_02_element_table(draft, out_dir),
        render_03_calculation_sheet(draft, out_dir),
        render_04_evidence_catalog(draft, out_dir),
        render_05_service_address_confirmation(draft, out_dir),
        render_06_procedural_attachments(draft, out_dir),
        render_07_hearing_playbook(draft, out_dir),
    ]
    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Standardized Chinese Labor Arbitration Docket (.docx 6-Pack)")
    parser.add_argument("draft_json", type=Path, help="Path to structured draft.json")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory to write generated .docx and .md files")
    args = parser.parse_args(argv)

    if not args.draft_json.is_file():
        print(f"error: draft_json not found: {args.draft_json}", file=sys.stderr)
        return 1

    created = generate_all_dockets(args.draft_json, args.output_dir)
    print(f"generate_docket_docx: OK ({len(created)} files generated)")
    for p in created:
        print(f"  - {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
