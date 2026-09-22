import streamlit as st
import pandas as pd
import json
import contextlib
import html
import importlib.util
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path
from streamlit_agraph import agraph, Node, Edge, Config

# 从 extractor.py 导入核心功能
from extractor import read_table, parse_test_case_string, generate_triples, infer_domain_from_name, build_grouped_rows, split_numbered_items, clean_cell

# --- CONFIG & STYLING ---


st.set_page_config(page_title="动态知识图谱构建器", layout="wide", page_icon="🧩")

# 定义颜色和图标，用于分类高亮
CATEGORY_STYLES = {
    "Test Case":      {"color": "#FFDE59", "icon": "🎯"}, # Yellow
    "Precondition":   {"color": "#FF6B6B", "icon": "📝"}, # Red
    "Precond Signal": {"color": "#FFA07A", "icon": "📡"}, # Light Salmon
    "Precond Value":  {"color": "#FFC0CB", "icon": "🔢"}, # Pink
    "Action":         {"color": "#48D1CC", "icon": "⚡️"}, # Medium Turquoise
    "Action Signal":  {"color": "#00CED1", "icon": "🕹️"}, # Dark Turquoise
    "Action Value":   {"color": "#AFEEEE", "icon": "🎛️"}, # Pale Turquoise
    "Expectation":    {"color": "#98FB98", "icon": "🌟"}, # Pale Green
    "Expect Signal":  {"color": "#3CB371", "icon": "📈"}, # Medium Sea Green
    "Expect Value":   {"color": "#9ACD32", "icon": "✅"}, # Yellow Green
    "Composite":      {"color": "#D3D3D3", "icon": "🔧"}, # Light Grey
    "Default":        {"color": "#1E90FF", "icon": "⚪️"}, # Dodger Blue
    "GrayedOut":      {"color": "#E0E0E0", "icon": "⚫️"}  # Very Light Grey for inactive
}

THEME_TONES = {
    "blue": ("#EEF4FF", "#3B82F6", "#1D4ED8"),
    "green": ("#ECFDF3", "#10B981", "#047857"),
    "amber": ("#FFFBEB", "#F59E0B", "#B45309"),
    "red": ("#FEF2F2", "#EF4444", "#B91C1C"),
    "purple": ("#F5F3FF", "#8B5CF6", "#6D28D9"),
}

def inject_global_styles():
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at top left, rgba(59,130,246,0.10), transparent 28%),
                radial-gradient(circle at top right, rgba(139,92,246,0.12), transparent 24%),
                linear-gradient(180deg, #f7f9fc 0%, #eef4ff 42%, #f8fafc 100%);
        }
        .main .block-container {
            max-width: 1480px;
            padding-top: 1.2rem;
            padding-bottom: 2.5rem;
        }
        .app-hero {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 0.35rem 0 1rem 0;
            margin-bottom: 0.8rem;
        }
        .app-hero-icon {
            width: 64px;
            height: 64px;
            border-radius: 999px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.8rem;
            margin-bottom: 0.8rem;
            background: linear-gradient(135deg, rgba(59,130,246,0.16), rgba(139,92,246,0.18));
            border: 1px solid rgba(59,130,246,0.16);
            box-shadow: 0 14px 34px rgba(59,130,246,0.10);
        }
        .app-hero-title {
            color: #0f172a;
            font-size: 1.9rem;
            font-weight: 900;
            letter-spacing: -0.03em;
            margin: 0;
        }
        .app-hero-subtitle {
            margin-top: 0.45rem;
            color: #64748b;
            font-size: 0.96rem;
            line-height: 1.7;
            max-width: 900px;
        }
        .section-head {
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
            margin: 0.6rem 0 0.85rem 0;
        }
        .section-head-title {
            font-size: 1.18rem;
            font-weight: 800;
            color: #0f172a;
            letter-spacing: -0.01em;
        }
        .section-head-subtitle {
            font-size: 0.98rem;
            color: #64748b;
        }
        div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stMarkdownContainer"] li {
            font-size: 0.98rem;
            line-height: 1.72;
        }
        label[data-testid="stWidgetLabel"] p,
        div[data-testid="stCaptionContainer"] p {
            font-size: 0.9rem;
        }
        .soft-card {
            background: rgba(255,255,255,0.75);
            border: 1px solid rgba(148,163,184,0.18);
            border-radius: 22px;
            padding: 18px 20px;
            box-shadow: 0 10px 32px rgba(15, 23, 42, 0.06);
            backdrop-filter: blur(6px);
            margin-bottom: 0.85rem;
        }
        .metric-card {
            border-radius: 22px;
            padding: 16px 18px;
            border: 1px solid rgba(148,163,184,0.16);
            box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
            margin-bottom: 0.65rem;
        }
        .metric-card-label {
            font-size: 0.88rem;
            font-weight: 700;
            opacity: 0.82;
            margin-bottom: 0.3rem;
        }
        .metric-card-value {
            font-size: 1.5rem;
            font-weight: 800;
            line-height: 1.2;
            word-break: break-word;
        }
        .metric-card-caption {
            margin-top: 0.32rem;
            font-size: 0.9rem;
            opacity: 0.86;
        }
        .info-kv {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.7rem;
            margin-top: 0.6rem;
            align-items: stretch;
        }
        .info-kv-item {
            background: rgba(255,255,255,0.68);
            border: 1px solid rgba(148,163,184,0.14);
            border-radius: 16px;
            padding: 0.85rem 0.95rem;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: flex-start;
        }
        .info-kv-label {
            color: #64748b;
            font-size: 0.82rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 0.24rem;
        }
        .info-kv-value {
            color: #0f172a;
            font-size: 1.03rem;
            font-weight: 700;
            line-height: 1.5;
            word-break: break-word;
        }
        .chip-group {
            margin: 0.65rem 0 0.2rem 0;
        }
        .chip-group-title {
            font-size: 0.9rem;
            font-weight: 700;
            color: #334155;
            margin-bottom: 0.45rem;
        }
        .chip-wrap {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
        }
        .chip {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.4rem 0.7rem;
            font-size: 0.88rem;
            font-weight: 700;
            border: 1px solid transparent;
        }
        .diff-card {
            border-radius: 18px;
            padding: 14px 16px;
            border: 1px solid rgba(148,163,184,0.14);
            margin-bottom: 0.55rem;
            box-shadow: 0 8px 22px rgba(15,23,42,0.05);
        }
        .diff-card-title {
            font-size: 0.9rem;
            font-weight: 800;
            margin-bottom: 0.35rem;
        }
        .diff-card-body {
            font-size: 1.02rem;
            font-weight: 700;
            color: #0f172a;
            line-height: 1.65;
            word-break: break-word;
        }
        [data-testid="stMetric"] {
            background: rgba(255,255,255,0.78);
            border: 1px solid rgba(148,163,184,0.18);
            border-radius: 22px;
            padding: 0.9rem 1rem;
            box-shadow: 0 12px 28px rgba(15,23,42,0.05);
        }
        [data-testid="stMetricLabel"] {
            font-weight: 700;
        }
        .stButton > button, .stDownloadButton > button {
            border-radius: 14px;
            border: 1px solid rgba(59,130,246,0.22);
            background: linear-gradient(135deg, #ffffff, #eef4ff);
            color: #0f172a;
            font-weight: 700;
            font-size: 0.96rem;
            padding: 0.62rem 1rem;
            box-shadow: 0 8px 20px rgba(59,130,246,0.08);
            transition: all 0.18s ease;
        }
        .stButton > button:hover, .stDownloadButton > button:hover {
            transform: translateY(-1px);
            border-color: rgba(59,130,246,0.4);
            box-shadow: 0 14px 28px rgba(59,130,246,0.14);
        }
        button[data-baseweb="tab"] {
            border-radius: 14px;
            padding: 0.55rem 0.95rem;
            margin-right: 0.4rem;
            background: rgba(255,255,255,0.65);
            border: 1px solid rgba(148,163,184,0.14);
            color: #475569;
            font-weight: 700;
            font-size: 0.94rem;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            background: linear-gradient(135deg, #dbeafe, #eef2ff);
            color: #1d4ed8;
            border-color: rgba(59,130,246,0.28);
            box-shadow: 0 8px 18px rgba(59,130,246,0.10);
        }
        [data-testid="stFileUploader"] {
            background: rgba(255,255,255,0.72);
            border: 1px dashed rgba(59,130,246,0.32);
            border-radius: 18px;
            padding: 0.35rem 0.55rem;
        }
        [data-baseweb="select"] > div,
        [data-baseweb="input"] > div {
            border-radius: 14px !important;
            border-color: rgba(148,163,184,0.28) !important;
            background: rgba(255,255,255,0.82) !important;
            box-shadow: none !important;
        }
        [data-baseweb="select"] * {
            font-size: 0.96rem !important;
        }
        [data-baseweb="input"] input {
            font-size: 0.96rem !important;
        }
        [data-testid="stDataFrame"], [data-testid="stTable"] {
            border-radius: 20px;
            overflow: hidden;
            border: 1px solid rgba(148,163,184,0.16);
            box-shadow: 0 14px 34px rgba(15,23,42,0.06);
            background: rgba(255,255,255,0.82);
        }
        [data-testid="stDataFrame"] * {
            font-size: 0.98rem !important;
        }
        [data-testid="stExpander"] {
            border: 1px solid rgba(148,163,184,0.16);
            border-radius: 18px;
            background: rgba(255,255,255,0.74);
            box-shadow: 0 10px 28px rgba(15,23,42,0.04);
        }
        [data-testid="stCodeBlock"] {
            border-radius: 18px;
            overflow: hidden;
            border: 1px solid rgba(148,163,184,0.16);
        }
        [data-testid="stCodeBlock"] pre,
        [data-testid="stCodeBlock"] code {
            font-size: 1rem !important;
            line-height: 1.72 !important;
        }
        [data-testid="stAlert"] {
            border-radius: 18px;
            border: 1px solid rgba(148,163,184,0.16);
            box-shadow: 0 10px 28px rgba(15,23,42,0.04);
        }
        .pdf-result-block {
            font-size: 1.05rem;
            line-height: 1.78;
            color: #0f172a;
        }
        .pdf-result-block code,
        .pdf-result-block pre {
            font-size: 1rem !important;
            line-height: 1.72 !important;
        }
        .pdf-result-block [data-testid="stMarkdownContainer"] p,
        .pdf-result-block [data-testid="stMarkdownContainer"] li,
        .pdf-result-block [data-testid="stCaptionContainer"] p {
            font-size: 1rem !important;
            line-height: 1.75 !important;
        }
        .pdf-result-block [data-testid="stDataFrame"] * {
            font-size: 0.98rem !important;
        }
        /* ── NHTSA Dashboard Styles ── */
        .nhtsa-hero {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            border-radius: 12px;
            padding: 28px 32px;
            margin-bottom: 1.2rem;
            color: #f1f5f9;
        }
        .nhtsa-hero-title {
            font-size: 1.65rem;
            font-weight: 800;
            color: #ffffff;
            margin-bottom: 0.3rem;
        }
        .nhtsa-hero-sub {
            font-size: 0.88rem;
            color: #94a3b8;
            line-height: 1.5;
        }
        .nhtsa-metric-row {
            display: flex;
            gap: 12px;
            margin-bottom: 1rem;
        }
        .nhtsa-metric {
            flex: 1;
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            padding: 16px 18px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        }
        .nhtsa-metric-value {
            font-size: 1.8rem;
            font-weight: 800;
            color: #0f172a;
        }
        .nhtsa-metric-label {
            font-size: 0.78rem;
            color: #64748b;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.03em;
            margin-top: 2px;
        }
        .nhtsa-metric-value.accent { color: #2563eb; }
        .nhtsa-metric-value.warn { color: #d97706; }
        .nhtsa-metric-value.good { color: #059669; }
        .nhtsa-panel {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 18px 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.04);
            margin-bottom: 1rem;
        }
        .nhtsa-panel-title {
            font-size: 0.92rem;
            font-weight: 800;
            color: #0f172a;
            margin-bottom: 0.6rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid #f1f5f9;
        }
        .risk-bar-row {
            display: flex;
            align-items: center;
            padding: 6px 0;
            border-bottom: 1px solid #f8fafc;
            font-size: 0.82rem;
        }
        .risk-bar-label {
            width: 130px;
            font-weight: 700;
            color: #334155;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .risk-bar-track {
            flex: 1;
            height: 20px;
            background: #f1f5f9;
            border-radius: 10px;
            margin: 0 10px;
            overflow: hidden;
        }
        .risk-bar-fill {
            height: 100%;
            border-radius: 10px;
            transition: width 0.4s;
        }
        .risk-bar-fill.critical { background: linear-gradient(90deg, #dc2626, #ef4444); }
        .risk-bar-fill.high { background: linear-gradient(90deg, #d97706, #f59e0b); }
        .risk-bar-fill.medium { background: linear-gradient(90deg, #2563eb, #3b82f6); }
        .risk-bar-fill.low { background: linear-gradient(90deg, #64748b, #94a3b8); }
        .risk-bar-score {
            width: 48px;
            text-align: right;
            font-weight: 800;
            font-size: 0.85rem;
            color: #0f172a;
        }
        .nhtsa-tag {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.02em;
        }
        .nhtsa-tag.ev { background: #dbeafe; color: #1e40af; }
        .nhtsa-tag.ice { background: #fef3c7; color: #92400e; }
        .rel-tag {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 6px;
            font-size: 0.76rem;
            font-weight: 700;
            margin: 2px;
        }
        .rel-tag.r1 { background: #dbeafe; color: #1e40af; }
        .rel-tag.r2 { background: #dcfce7; color: #166534; }
        .rel-tag.r3 { background: #fef3c7; color: #92400e; }
        .rel-tag.r4 { background: #fce7f3; color: #9d174d; }
        .rel-tag.r5 { background: #e0e7ff; color: #3730a3; }
        .rel-tag.r6 { background: #f0fdf4; color: #14532d; }
        /* ── Skill card styles ── */
        .skill-card {
            background: #ffffff;
            border: 1px solid #dfe7f2;
            border-radius: 8px;
            padding: 13px 14px;
            min-height: 132px;
            box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
        }
        .skill-id {
            color: #1d4ed8;
            font-size: 0.78rem;
            font-weight: 800;
            word-break: break-all;
        }
        .skill-name {
            color: #111827;
            font-size: 0.98rem;
            font-weight: 800;
            margin: 0.25rem 0;
        }
        .skill-desc {
            color: #64748b;
            font-size: 0.84rem;
            line-height: 1.45;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def _tone_styles(tone):
    return THEME_TONES.get(tone, THEME_TONES["blue"])

def render_hero_banner(title, subtitle, icon="🧩", align="center", compact=False):
    is_left = align == "left"
    container_style = "align-items:flex-start; text-align:left;" if is_left else "align-items:center; text-align:center;"
    icon_size = "46px" if compact else "64px"
    icon_font_size = "1.2rem" if compact else "1.8rem"
    title_size = "1.28rem" if compact else "1.9rem"
    subtitle_width = "100%" if is_left else "900px"
    subtitle_size = "0.88rem" if compact else "0.96rem"
    st.markdown(
        f"""
        <div class="app-hero" style="{container_style}">
            <div class="app-hero-icon" style="width:{icon_size}; height:{icon_size}; font-size:{icon_font_size}; margin-bottom:{'0.55rem' if compact else '0.8rem'};">{html.escape(icon)}</div>
            <div class="app-hero-title" style="font-size:{title_size};">{html.escape(title)}</div>
            <div class="app-hero-subtitle" style="max-width:{subtitle_width}; font-size:{subtitle_size};">{html.escape(subtitle)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def render_section_header(title, subtitle=""):
    subtitle_html = f'<div class="section-head-subtitle">{html.escape(subtitle)}</div>' if subtitle else ""
    st.markdown(
        f"""
        <div class="section-head">
            <div class="section-head-title">{html.escape(title)}</div>
            {subtitle_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

def render_metric_card(title, value, caption="", tone="blue"):
    bg, accent, text = _tone_styles(tone)
    caption_html = f'<div class="metric-card-caption">{html.escape(caption)}</div>' if caption else ""
    st.markdown(
        f"""
        <div class="metric-card" style="background:{bg}; border-color:{accent}22;">
            <div class="metric-card-label" style="color:{text};">{html.escape(title)}</div>
            <div class="metric-card-value" style="color:{text};">{html.escape(str(value))}</div>
            {caption_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

def render_kv_panel(items, tone="blue"):
    bg, accent, text = _tone_styles(tone)
    item_html = "".join(
        f"<div class=\"info-kv-item\"><div class=\"info-kv-label\">{html.escape(str(label))}</div><div class=\"info-kv-value\">{html.escape(str(value))}</div></div>"
        for label, value in items
    )
    st.markdown(
        f"""
        <div class="soft-card" style="background:{bg}; border-color:{accent}22;">
            <div class="info-kv">{item_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def render_toggle_kv_panel(toggle_label, items, tone="blue", key="show_details", default=False):
    show_details = st.toggle(toggle_label, value=default, key=key)
    if show_details:
        render_kv_panel(items, tone=tone)

def current_log_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def append_operation_history(history_key, text_key, action, detail_lines=None, status="完成"):
    detail_lines = detail_lines or []
    timestamp = current_log_timestamp()
    history = list(st.session_state.get(history_key, []))
    history.append({
        "时间": timestamp,
        "操作": action,
        "结果": status,
        "说明": " | ".join(str(line) for line in detail_lines[:3]) if detail_lines else "-",
    })
    st.session_state[history_key] = history

    text_lines = list(st.session_state.get(text_key, []))
    text_lines.append(f"[{timestamp}] {action}（{status}）")
    for line in detail_lines:
        text_lines.append(f"  - {line}")
    st.session_state[text_key] = text_lines

def render_operation_history(history_key, empty_message):
    history = st.session_state.get(history_key, [])
    if history:
        st.dataframe(pd.DataFrame(history), width='stretch', hide_index=True)
    else:
        st.caption(empty_message)

def render_chip_group(title, values, tone="blue", empty_text="无"):
    bg, accent, text = _tone_styles(tone)
    chips = values if values else [empty_text]
    chip_html = "".join(
        f"<span class=\"chip\" style=\"background:{bg}; border-color:{accent}33; color:{text};\">{html.escape(str(value))}</span>"
        for value in chips
    )
    st.markdown(
        f"""
        <div class="chip-group">
            <div class="chip-group-title">{html.escape(title)}</div>
            <div class="chip-wrap">{chip_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def render_diff_triplet_card(title, triple_text, tone="blue"):
    bg, accent, text = _tone_styles(tone)
    st.markdown(
        f"""
        <div class="diff-card" style="background:{bg}; border-color:{accent}26;">
            <div class="diff-card-title" style="color:{text};">{html.escape(title)}</div>
            <div class="diff-card-body">{html.escape(triple_text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

ROOT = Path(__file__).resolve().parent  # 7.27/
VISUAL_EXTRACTOR_PATH = ROOT / "extractor.py"
PDF_PIPELINE_ROOT = ROOT / "pdf_pipeline"
PDF_CONFIG_PATH = ROOT / "pdf_pipeline" / "config" / "pipeline_config.json"
PDF_MANIFEST_PATH = ROOT / "pdf_pipeline" / "data" / "manifests" / "image_manifest.json"
PDF_INTERMEDIATE_ROOT = ROOT / "pdf_pipeline" / "data" / "intermediate"
INCREMENTAL_SCRIPT_PATH = ROOT / "incremental.py"
INCREMENTAL_DOMAINS_ROOT = ROOT / "domains"
WORKBENCH_OUTPUT_ROOT = ROOT / "workbench_outputs"
WORKBENCH_EXCEL_ROOT = WORKBENCH_OUTPUT_ROOT / "excel"
WORKBENCH_PDF_ROOT = WORKBENCH_OUTPUT_ROOT / "pdf"
WORKBENCH_INCREMENTAL_ROOT = WORKBENCH_OUTPUT_ROOT / "incremental"
SKILL_REGISTRY_PATH = ROOT / "agentic_kg" / "memory" / "skill_registry.json"
PENDING_SKILLS_ROOT = ROOT / "agentic_kg" / "skills" / "pending"
NHTSA_DATA_DIR = ROOT / "nhtsa_data"


def resolve_project_path(path_text: str) -> Path:
    """将旧部署绝对路径映射到当前 7.30_kg 目录（自包含部署）。"""
    text = str(path_text or "")

    linux_prefix = "/home/dt/智己项目"
    if text.startswith(linux_prefix):
        mapped = ROOT / text[len(linux_prefix):].lstrip("/\\")
        if mapped.exists():
            return mapped

    marker = "智己项目/"
    normalized = text.replace("\\", "/")
    if marker in normalized:
        mapped = ROOT / normalized.split(marker, 1)[1]
        if mapped.exists():
            return mapped

    candidate = Path(text)
    if candidate.exists():
        return candidate
    return candidate

# ── API Key ──
import os
os.environ.setdefault("DASHSCOPE_API_KEY", "")

for output_root in [WORKBENCH_OUTPUT_ROOT, WORKBENCH_EXCEL_ROOT, WORKBENCH_PDF_ROOT, WORKBENCH_INCREMENTAL_ROOT]:
    output_root.mkdir(parents=True, exist_ok=True)

# ── Skill 匹配辅助函数 ──

def load_skill_registry() -> list:
    if not SKILL_REGISTRY_PATH.exists():
        return []
    return json.loads(SKILL_REGISTRY_PATH.read_text(encoding="utf-8"))


def match_excel_skill(domain_name: str) -> dict | None:
    """根据业务域名称匹配 Excel 抽取 Skill。"""
    registry = load_skill_registry()
    for skill in registry:
        if skill.get("file_type") != "excel":
            continue
        if domain_name == "离车上锁功能测试" and skill["template_kind"] == "lock_test_case":
            return skill
        if domain_name != "离车上锁功能测试" and skill["template_kind"] == "grouped_test_case":
            return skill
    return None


def match_pdf_extraction_skill() -> dict | None:
    registry = load_skill_registry()
    for skill in registry:
        if skill["skill_id"] == "pdf.online_table_pipeline.v1":
            return skill
    return None


def match_pdf_fusion_skill() -> dict | None:
    registry = load_skill_registry()
    for skill in registry:
        if skill["skill_id"] == "fusion.semantic_dedup_conflict.v1":
            return skill
    return None


def render_skill_card(skill: dict, matched: bool = True):
    """渲染技能卡片，展示技能匹配结果。"""
    status_label = "✅ 已命中" if matched else "⚠️ 待审核"
    status_color = "#059669" if matched else "#d97706"
    bg = "#f0fdf4" if matched else "#fffbeb"
    st.markdown(
        f"""
        <div style="background:{bg};border:1px solid #d1d5db;border-radius:12px;padding:12px 15px;margin:8px 0;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
            <span style="font-size:0.78rem;font-weight:800;color:{status_color};">{status_label}</span>
            <span style="font-size:0.82rem;font-weight:700;color:#1d4ed8;">{skill.get('skill_id', '')}</span>
          </div>
          <div style="font-size:0.92rem;font-weight:800;color:#111827;margin:2px 0;">{skill.get('name', '')}</div>
          <div style="font-size:0.78rem;color:#64748b;line-height:1.4;">{skill.get('description', '')}</div>
          <div style="font-size:0.75rem;color:#9ca3af;margin-top:2px;">工具: {skill.get('tool', '-')} | 模板: {skill.get('template_kind', '-')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# --- SESSION STATE INITIALIZATION ---

if 'df' not in st.session_state:
    st.session_state.df = None
    st.session_state.case_records = None
    st.session_state.domain_name = ""
    st.session_state.uploaded_file_name = ""
    st.session_state.current_row = -1
    st.session_state.all_nodes = set()
    st.session_state.all_edges = []
    st.session_state.last_added_triples = []
    st.session_state.previous_triples = [] # For diff comparison
    st.session_state.search_term = ""
    st.session_state.highlight_cases = [] # For test case highlighting
    st.session_state.display_mode = "Full Graph" # New state for display mode
    st.session_state.pdf_doc_name = ""
    st.session_state.pdf_image_index = 0
    st.session_state.pdf_last_run_logs = []
    st.session_state.pdf_last_run_image_id = ""
    st.session_state.pdf_last_export_dir = ""
    st.session_state.pdf_results_visible = False
    st.session_state.pdf_loaded_result_key = ""
    st.session_state.pdf_operation_history = []
    st.session_state.pdf_operation_text_logs = []
    st.session_state.excel_last_export_path = ""
    st.session_state.excel_reviewed_rows = []
    st.session_state.llm_analysis = None
    st.session_state.llm_analysis = None
    st.session_state.llm_reextracted = None
    st.session_state.excel_last_review_path = ""
    st.session_state.pdf_llm_triples = None
    st.session_state.pdf_last_review_path = ""
    st.session_state.incremental_last_export_dir = ""
    st.session_state.incremental_results_visible = False
    st.session_state.incremental_loaded_domain = ""
    st.session_state.incremental_display_bundle = None
    st.session_state.incremental_result_source = ""
    st.session_state.incremental_last_logs = []
    st.session_state.incremental_operation_history = []
    st.session_state.incremental_selected_case_key = ""

# --- HELPER FUNCTIONS ---

def reset_state():
    """重置整个应用状态"""
    st.session_state.df = None
    st.session_state.case_records = None
    st.session_state.domain_name = ""
    st.session_state.uploaded_file_name = ""
    st.session_state.current_row = -1
    st.session_state.all_nodes = set()
    st.session_state.all_edges = []
    st.session_state.last_added_triples = []
    st.session_state.previous_triples = []
    st.session_state.search_term = ""
    st.session_state.highlight_cases = []
    st.session_state.display_mode = "Full Graph"
    st.session_state.excel_last_export_path = ""
    st.session_state.excel_reviewed_rows = []
    st.session_state.llm_analysis = None
    st.session_state.llm_analysis = None
    st.session_state.excel_last_review_path = ""
    st.session_state.incremental_display_bundle = None
    st.session_state.incremental_result_source = ""

def set_incremental_display_bundle(domain_dir, source):
    domain_path = Path(domain_dir)
    st.session_state.incremental_display_bundle = load_incremental_domain_bundle(domain_path)
    st.session_state.incremental_results_visible = True
    st.session_state.incremental_loaded_domain = str(domain_path)
    st.session_state.incremental_result_source = source
    st.session_state.incremental_selected_case_key = ""

def ensure_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path

def current_timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def write_json_output(path, payload):
    path = Path(path)
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

def write_text_output(path, text):
    path = Path(path)
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")
    return path


def normalize_triple_rows(triples):
    rows = []
    for index, item in enumerate(triples or [], start=1):
        if isinstance(item, dict):
            row = dict(item)
            row.setdefault("head", "")
            row.setdefault("relation", "")
            row.setdefault("tail", "")
        elif isinstance(item, (list, tuple)) and len(item) >= 3:
            row = {"head": item[0], "relation": item[1], "tail": item[2]}
        else:
            continue
        row = {key: ("" if value is None else value) for key, value in row.items()}
        row["keep"] = True
        row["review_note"] = ""
        row["idx"] = index
        rows.append(row)
    return rows


def review_rows_to_triples(review_df, output_format="tuple"):
    if review_df is None or review_df.empty:
        return []
    reviewed = []
    for _, row in review_df.iterrows():
        if not bool(row.get("keep", True)):
            continue
        head = clean_cell(row.get("head", ""))
        relation = clean_cell(row.get("relation", ""))
        tail = clean_cell(row.get("tail", ""))
        if not (head and relation and tail):
            continue
        if output_format == "dict":
            payload = {"head": head, "relation": relation, "tail": tail}
            for key in ["triple_type", "confidence_note", "conflict", "source", "evidence", "review_note"]:
                if key in row and str(row.get(key, "")).strip():
                    payload[key] = row.get(key)
            reviewed.append(payload)
        else:
            reviewed.append((head, relation, tail))
    return reviewed


def render_triple_review_editor(title, subtitle, triples, key, output_format="tuple"):
    render_section_header(title, subtitle)
    rows = normalize_triple_rows(triples)
    if not rows:
        st.warning("\u5f53\u524d\u6ca1\u6709\u53ef\u6821\u9a8c\u7684\u4e09\u5143\u7ec4\u3002")
        return [], {"raw_count": 0, "reviewed_count": 0, "removed_count": 0}
    review_df = pd.DataFrame(rows)
    # 过滤全空/全null列，保留有实际内容的列
    review_df = review_df.loc[:, [col for col in review_df.columns if review_df[col].replace("", pd.NA).notna().any() or col in ("keep", "head", "relation", "tail", "idx")]]
    preferred_cols = ["keep", "idx", "head", "relation", "tail", "triple_type", "confidence_note", "conflict", "review_note"]
    display_cols = [col for col in preferred_cols if col in review_df.columns]
    display_cols += [col for col in review_df.columns if col not in display_cols]
    edited_df = st.data_editor(
        review_df[display_cols],
        width='stretch',
        hide_index=True,
        num_rows="dynamic",
        key=key,
        column_config={
            "keep": st.column_config.CheckboxColumn("\u786e\u8ba4\u4fdd\u5b58", help="\u53d6\u6d88\u52fe\u9009\u540e\uff0c\u8be5\u6761\u4e0d\u4f1a\u8fdb\u5165\u5ba1\u6838\u7248\u7ed3\u679c\u3002", default=True),
            "idx": st.column_config.NumberColumn("\u5e8f\u53f7", width="small"),
            "head": st.column_config.TextColumn("\u5b9e\u4f53 head", required=True, width="medium"),
            "relation": st.column_config.TextColumn("\u5173\u7cfb relation", required=True, width="small"),
            "tail": st.column_config.TextColumn("\u5b9e\u4f53 tail", required=True, width="large"),
            "review_note": st.column_config.TextColumn("\u5ba1\u6838\u5907\u6ce8", width="medium"),
        },
        disabled=[col for col in ["idx", "triple_type", "confidence_note", "conflict"] if col in review_df.columns],
    )
    reviewed = review_rows_to_triples(edited_df, output_format=output_format)
    removed_count = len(rows) - len(reviewed)
    m1, m2, m3 = st.columns(3)
    m1.metric("\u539f\u59cb\u6761\u6570", len(rows))
    m2.metric("\u786e\u8ba4\u4fdd\u5b58", len(reviewed))
    m3.metric("\u5220\u9664/\u7a7a\u503c", removed_count)
    return reviewed, {"raw_count": len(rows), "reviewed_count": len(reviewed), "removed_count": removed_count}


def save_excel_case_review(domain_name, source_name, row_info, reviewed_triples, review_summary):
    review_dir = ensure_dir(WORKBENCH_EXCEL_ROOT / sanitize_path_component(domain_name) / sanitize_path_component(Path(source_name or domain_name).stem) / "reviewed_cases")
    timestamp = current_timestamp()
    payload = {
        "domain_name": domain_name,
        "source_name": source_name,
        "review_time": timestamp,
        "row": row_info.get("row"),
        "case_name": row_info.get("case_name", ""),
        "summary": review_summary,
        "triples": [{"head": h, "relation": r, "tail": t} for h, r, t in reviewed_triples],
    }
    row_token = sanitize_path_component(f"row_{row_info.get('row', 'unknown')}")
    review_path = review_dir / f"{row_token}_{timestamp}.json"
    write_json_output(review_path, payload)
    write_json_output(review_dir / f"{row_token}_latest.json", payload)
    return review_path


def save_pdf_triple_review(item, reviewed_triples, review_summary, source_stage):
    timestamp = current_timestamp()
    review_dir = ensure_dir(WORKBENCH_PDF_ROOT / sanitize_path_component(item.get("doc_name", "\u672a\u547d\u540d\u6587\u6863")) / sanitize_path_component(item.get("image_id", "unknown_image")) / "reviewed_triples")
    payload = {
        "doc_name": item.get("doc_name", ""),
        "image_id": item.get("image_id", ""),
        "file_name": item.get("file_name", ""),
        "source_stage": source_stage,
        "review_time": timestamp,
        "summary": review_summary,
        "triples": reviewed_triples,
    }
    review_path = review_dir / f"reviewed_{timestamp}.json"
    write_json_output(review_path, payload)
    write_json_output(review_dir / "reviewed_latest.json", payload)
    return review_path


def copy_file_if_exists(source_path, target_path):
    source = Path(source_path)
    target = Path(target_path)
    if not source.exists():
        return False
    ensure_dir(target.parent)
    shutil.copy2(source, target)
    return True

def save_uploaded_file(uploaded_file, target_dir):
    target_dir = ensure_dir(target_dir)
    target_path = target_dir / uploaded_file.name
    target_path.write_bytes(uploaded_file.getvalue())
    return target_path

def load_json_file(path, default):
    file_path = Path(path)
    if not file_path.exists():
        return default
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return default

def load_text_file(path, default=""):
    file_path = Path(path)
    if not file_path.exists():
        return default
    try:
        return file_path.read_text(encoding="utf-8")
    except Exception:
        return default

def sanitize_path_component(value):
    sanitized = re.sub(r'[\\/:*?"<>|]+', "_", str(value)).strip()
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized or "unnamed"

def load_jsonl_file(path):
    file_path = Path(path)
    if not file_path.exists():
        return []
    records = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            records.append(json.loads(text))
        except json.JSONDecodeError:
            continue
    return records

def incremental_record_identity(record):
    record_type = record.get("record_type", "")
    case_key = record.get("case_key", "")
    if record_type == "changed_pair":
        old_triple = record.get("old_triple", {})
        new_triple = record.get("new_triple", {})
        return (
            record_type,
            case_key,
            old_triple.get("fact_hash", ""),
            new_triple.get("fact_hash", ""),
            old_triple.get("head", ""),
            old_triple.get("relation", ""),
            old_triple.get("tail", ""),
            new_triple.get("head", ""),
            new_triple.get("relation", ""),
            new_triple.get("tail", ""),
        )
    if record_type == "case_marker":
        return (record_type, case_key)
    return (
        record_type,
        case_key,
        record.get("fact_hash", ""),
        record.get("head", ""),
        record.get("relation", ""),
        record.get("tail", ""),
    )

def deduplicate_incremental_records(records):
    deduped_records = []
    seen = set()
    for record in records:
        record_id = incremental_record_identity(record)
        if record_id in seen:
            continue
        seen.add(record_id)
        deduped_records.append(record)
    return deduped_records

def get_incremental_runtime_cache_key():
    incremental_mtime = INCREMENTAL_SCRIPT_PATH.stat().st_mtime_ns if INCREMENTAL_SCRIPT_PATH.exists() else 0
    extractor_mtime = VISUAL_EXTRACTOR_PATH.stat().st_mtime_ns if VISUAL_EXTRACTOR_PATH.exists() else 0
    return (incremental_mtime, extractor_mtime)

@st.cache_resource(show_spinner=False)
def load_incremental_runtime_modules(cache_key):
    if not INCREMENTAL_SCRIPT_PATH.exists():
        raise FileNotFoundError(f"未找到增量更新脚本：{INCREMENTAL_SCRIPT_PATH}")
    spec = importlib.util.spec_from_file_location("visualize_incremental_runtime", str(INCREMENTAL_SCRIPT_PATH))
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载增量更新脚本：{INCREMENTAL_SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {
        "module": module,
        "initialize_current_baseline": module.initialize_current_baseline,
        "process_candidate_excel": module.process_candidate_excel,
        "apply_domain_pending": module.apply_domain_pending,
    }

def get_incremental_domain_dirs():
    if not INCREMENTAL_DOMAINS_ROOT.exists():
        return []
    return sorted([path for path in INCREMENTAL_DOMAINS_ROOT.iterdir() if path.is_dir()], key=lambda item: item.name)

def infer_incremental_domain_name(domain_dir):
    domain_path = Path(domain_dir)
    candidate_files = [
        domain_path / "pending_add_triples.jsonl",
        domain_path / "pending_remove_triples.jsonl",
        domain_path / "pending_changed_triples.jsonl",
        domain_path / "current_case_index.jsonl",
        domain_path / "current_triples.jsonl",
    ]
    for candidate_file in candidate_files:
        records = load_jsonl_file(candidate_file)
        if records and records[0].get("domain"):
            return records[0]["domain"]
    name_parts = domain_path.name.split("_", 2)
    if len(name_parts) == 3:
        return name_parts[2]
    return domain_path.name

def resolve_incremental_domain_dir(domain_name):
    for domain_dir in get_incremental_domain_dirs():
        inferred_name = infer_incremental_domain_name(domain_dir)
        if inferred_name == domain_name or domain_dir.name.endswith(domain_name):
            return domain_dir
    return INCREMENTAL_DOMAINS_ROOT / sanitize_path_component(domain_name)

def load_incremental_domain_bundle(domain_dir):
    domain_path = Path(domain_dir)
    return {
        "domain_dir": domain_path,
        "domain_name": infer_incremental_domain_name(domain_path),
        "pending_add": load_jsonl_file(domain_path / "pending_add_triples.jsonl"),
        "pending_remove": load_jsonl_file(domain_path / "pending_remove_triples.jsonl"),
        "pending_changed": load_jsonl_file(domain_path / "pending_changed_triples.jsonl"),
        "current_case_index": load_jsonl_file(domain_path / "current_case_index.jsonl"),
        "current_triples": load_jsonl_file(domain_path / "current_triples.jsonl"),
    }

def build_incremental_case_summaries(bundle):
    case_map = {}
    pending_add_records = deduplicate_incremental_records(bundle["pending_add"])
    pending_remove_records = deduplicate_incremental_records(bundle["pending_remove"])
    pending_changed_records = deduplicate_incremental_records(bundle["pending_changed"])

    def ensure_case_entry(record):
        case_key = record.get("case_key", "")
        if case_key not in case_map:
            case_map[case_key] = {
                "case_key": case_key,
                "row": record.get("row", 0),
                "case_id": record.get("case_id", ""),
                "case_name": record.get("case_name", "未命名案例"),
                "case_anchor": record.get("case_anchor", ""),
                "domain": record.get("domain", bundle.get("domain_name", "")),
                "new_case": False,
                "add_count": 0,
                "remove_count": 0,
                "changed_count": 0,
                "change_types": set(),
            }
        return case_map[case_key]

    for record in pending_add_records:
        entry = ensure_case_entry(record)
        entry["change_types"].add(record.get("change_type", "add"))
        if record.get("record_type") == "case_marker":
            entry["new_case"] = True
        elif record.get("record_type") == "triple":
            entry["add_count"] += 1

    for record in pending_remove_records:
        entry = ensure_case_entry(record)
        entry["change_types"].add(record.get("change_type", "remove"))
        entry["remove_count"] += 1

    for record in pending_changed_records:
        entry = ensure_case_entry(record)
        entry["change_types"].add(record.get("change_type", "logic_change"))
        entry["changed_count"] += 1

    summaries = []
    for entry in case_map.values():
        entry["change_types"] = " / ".join(sorted(entry["change_types"]))
        entry["net_delta"] = entry["add_count"] - entry["remove_count"]
        summaries.append(entry)
    summaries.sort(key=lambda item: (item["row"], item["case_name"], item["case_key"]))
    return summaries

def build_incremental_relation_summary(bundle):
    add_rel = Counter(record.get("relation", "未知关系") for record in bundle["pending_add"] if record.get("record_type") == "triple")
    remove_rel = Counter(record.get("relation", "未知关系") for record in bundle["pending_remove"])
    changed_rel = Counter(record.get("new_triple", {}).get("relation") or record.get("old_triple", {}).get("relation") or "未知关系" for record in bundle["pending_changed"])
    rows = []
    for relation in sorted(set(add_rel) | set(remove_rel) | set(changed_rel)):
        rows.append({
            "relation": relation,
            "待增加": add_rel.get(relation, 0),
            "待删除": remove_rel.get(relation, 0),
            "待更新": changed_rel.get(relation, 0),
        })
    return pd.DataFrame(rows)

def get_incremental_case_detail(bundle, case_key):
    add_records = [record for record in deduplicate_incremental_records(bundle["pending_add"]) if record.get("case_key") == case_key and record.get("record_type") == "triple"]
    remove_records = [record for record in deduplicate_incremental_records(bundle["pending_remove"]) if record.get("case_key") == case_key]
    changed_records = [record for record in deduplicate_incremental_records(bundle["pending_changed"]) if record.get("case_key") == case_key]
    case_marker = next((record for record in deduplicate_incremental_records(bundle["pending_add"]) if record.get("case_key") == case_key and record.get("record_type") == "case_marker"), None)
    return {
        "add_records": add_records,
        "remove_records": remove_records,
        "changed_records": changed_records,
        "case_marker": case_marker,
    }

def build_incremental_diff_graph(case_summary, case_detail):
    nodes = []
    edges = []
    seen_nodes = set()

    def add_node(node_id, label, color, size=18):
        if node_id in seen_nodes:
            return
        seen_nodes.add(node_id)
        nodes.append(Node(id=node_id, label=label, color=color, size=size))

    case_node_id = f"case::{case_summary['case_key']}"
    add_node(case_node_id, case_summary["case_name"], "#1F4E79", size=26)

    for record in case_detail["remove_records"]:
        head_id = f"remove::{record['fact_hash']}::head"
        tail_id = f"remove::{record['fact_hash']}::tail"
        add_node(head_id, record.get("head", ""), "#F28B82")
        add_node(tail_id, record.get("tail", ""), "#F28B82")
        edges.append(Edge(source=case_node_id, target=head_id, label="待删除", color="#D93025"))
        edges.append(Edge(source=head_id, target=tail_id, label=record.get("relation", ""), color="#D93025"))

    for record in case_detail["add_records"]:
        head_id = f"add::{record['fact_hash']}::head"
        tail_id = f"add::{record['fact_hash']}::tail"
        add_node(head_id, record.get("head", ""), "#81C995")
        add_node(tail_id, record.get("tail", ""), "#81C995")
        edges.append(Edge(source=case_node_id, target=head_id, label="待增加", color="#188038"))
        edges.append(Edge(source=head_id, target=tail_id, label=record.get("relation", ""), color="#188038"))

    for index, record in enumerate(case_detail["changed_records"], start=1):
        old_triple = record.get("old_triple", {})
        new_triple = record.get("new_triple", {})
        old_head_id = f"changed_old::{index}::{old_triple.get('fact_hash', index)}::head"
        old_tail_id = f"changed_old::{index}::{old_triple.get('fact_hash', index)}::tail"
        new_head_id = f"changed_new::{index}::{new_triple.get('fact_hash', index)}::head"
        new_tail_id = f"changed_new::{index}::{new_triple.get('fact_hash', index)}::tail"
        add_node(old_head_id, f"旧:{old_triple.get('head', '')}", "#F6BF26")
        add_node(old_tail_id, f"旧:{old_triple.get('tail', '')}", "#F6BF26")
        add_node(new_head_id, f"新:{new_triple.get('head', '')}", "#34A853")
        add_node(new_tail_id, f"新:{new_triple.get('tail', '')}", "#34A853")
        edges.append(Edge(source=case_node_id, target=old_head_id, label="旧逻辑", color="#FB8C00"))
        edges.append(Edge(source=old_head_id, target=old_tail_id, label=old_triple.get("relation", ""), color="#FB8C00"))
        edges.append(Edge(source=case_node_id, target=new_head_id, label="新逻辑", color="#0F9D58"))
        edges.append(Edge(source=new_head_id, target=new_tail_id, label=new_triple.get("relation", ""), color="#0F9D58"))

    return nodes, edges

def build_incremental_category_graph(case_summary, case_detail, mode):
    nodes = []
    edges = []
    seen_nodes = set()

    def add_node(node_id, label, color, size=20):
        if node_id in seen_nodes:
            return
        seen_nodes.add(node_id)
        nodes.append(Node(id=node_id, label=label, color=color, size=size))

    def add_triplet(prefix, triple, node_color, edge_color, case_label, label_prefix=""):
        head_value = triple.get("head", "未命名头实体")
        tail_value = triple.get("tail", "未命名尾实体")
        relation_value = triple.get("relation", "未命名关系")
        head_id = f"{prefix}::head::{head_value}"
        tail_id = f"{prefix}::tail::{tail_value}"
        add_node(head_id, f"{label_prefix}{head_value}", node_color, size=20)
        add_node(tail_id, f"{label_prefix}{tail_value}", node_color, size=20)
        edges.append(Edge(source=case_node_id, target=head_id, label=case_label, color=edge_color))
        edges.append(Edge(source=head_id, target=tail_id, label=relation_value, color=edge_color))
        return head_id, tail_id, relation_value

    case_node_id = f"case::{case_summary['case_key']}::{mode}"
    add_node(case_node_id, case_summary["case_name"], "#D8E8FF", size=28)

    if mode == "add":
        for record in case_detail["add_records"]:
            add_triplet(
                f"add::{record['fact_hash']}",
                record,
                "#E2F5EA",
                "#8CC6A6",
                "待增加",
            )
    elif mode == "remove":
        for record in case_detail["remove_records"]:
            add_triplet(
                f"remove::{record['fact_hash']}",
                record,
                "#FBE7E7",
                "#E7A8A8",
                "待删除",
            )
    elif mode == "changed":
        for index, record in enumerate(case_detail["changed_records"], start=1):
            old_triple = record.get("old_triple", {})
            new_triple = record.get("new_triple", {})
            change_node_id = f"change::{case_summary['case_key']}::{index}"
            old_relation = old_triple.get("relation", "")
            new_relation = new_triple.get("relation", "")
            add_node(change_node_id, f"逻辑变更 {index}", "#F1E8FF", size=22)
            edges.append(Edge(source=case_node_id, target=change_node_id, label="逻辑变更", color="#C7B0F6"))
            old_head_id, old_tail_id, _ = add_triplet(
                f"changed-old::{case_summary['case_key']}::{index}",
                old_triple,
                "#FFF3DE",
                "#E5C28A",
                "变更前",
                label_prefix="旧：",
            )
            new_head_id, new_tail_id, _ = add_triplet(
                f"changed-new::{case_summary['case_key']}::{index}",
                new_triple,
                "#E6F6ED",
                "#9DCCB0",
                "变更后",
                label_prefix="新：",
            )
            edges.append(Edge(source=change_node_id, target=old_head_id, label="旧逻辑", color="#E5C28A"))
            edges.append(Edge(source=change_node_id, target=new_head_id, label="新逻辑", color="#9DCCB0"))
            transition_label = f"{old_relation} → {new_relation}" if old_relation != new_relation else "逻辑内容变更"
            edges.append(Edge(source=old_head_id, target=new_head_id, label=transition_label, color="#C7B0F6"))
            if old_tail_id != new_tail_id:
                edges.append(Edge(source=old_tail_id, target=new_tail_id, label="尾实体变化", color="#D5C3F6"))

    return nodes, edges

def flatten_incremental_records(records):
    if not records:
        return pd.DataFrame()
    normalized_rows = []
    for record in records:
        normalized_rows.append({
            "row": record.get("row", ""),
            "case_name": record.get("case_name", ""),
            "case_id": record.get("case_id", ""),
            "change_type": record.get("change_type", ""),
            "head": record.get("head", ""),
            "relation": record.get("relation", ""),
            "tail": record.get("tail", ""),
            "fact_hash": record.get("fact_hash", ""),
            "case_key": record.get("case_key", ""),
        })
    return pd.DataFrame(normalized_rows)

def flatten_changed_records(records):
    if not records:
        return pd.DataFrame()
    normalized_rows = []
    for record in records:
        normalized_rows.append({
            "row": record.get("row", ""),
            "case_name": record.get("case_name", ""),
            "case_id": record.get("case_id", ""),
            "relation": record.get("new_triple", {}).get("relation") or record.get("old_triple", {}).get("relation"),
            "old_head": record.get("old_triple", {}).get("head", ""),
            "old_tail": record.get("old_triple", {}).get("tail", ""),
            "new_head": record.get("new_triple", {}).get("head", ""),
            "new_tail": record.get("new_triple", {}).get("tail", ""),
            "case_key": record.get("case_key", ""),
        })
    return pd.DataFrame(normalized_rows)

def export_incremental_snapshot(bundle, case_summaries):
    domain_name = bundle.get("domain_name", "未命名领域")
    timestamp = current_timestamp()
    export_dir = ensure_dir(WORKBENCH_INCREMENTAL_ROOT / sanitize_path_component(domain_name) / timestamp)
    for file_name in ["pending_add_triples.jsonl", "pending_remove_triples.jsonl", "pending_changed_triples.jsonl", "current_case_index.jsonl", "current_triples.jsonl"]:
        copy_file_if_exists(bundle["domain_dir"] / file_name, export_dir / file_name)
    write_json_output(export_dir / "case_summaries.json", case_summaries)
    write_json_output(
        export_dir / "summary.json",
        {
            "domain_name": domain_name,
            "export_time": timestamp,
            "pending_add_count": len(bundle["pending_add"]),
            "pending_remove_count": len(bundle["pending_remove"]),
            "pending_changed_count": len(bundle["pending_changed"]),
            "case_count": len(case_summaries),
            "domain_dir": str(bundle["domain_dir"]),
        },
    )
    if st.session_state.incremental_last_logs:
        write_text_output(export_dir / "process_log.txt", "\n".join(st.session_state.incremental_last_logs))
    return export_dir

@st.cache_resource(show_spinner=False)
def load_pdf_runtime_modules():
    src_root = PDF_PIPELINE_ROOT / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from step2_ocr import run_ocr
    from step3_desc import generate_descriptions
    from step4_extract import extract_triples
    from step5_fuse import fuse_triples
    from utils.env_utils import load_local_env, require_env
    return {
        "run_ocr": run_ocr,
        "generate_descriptions": generate_descriptions,
        "extract_triples": extract_triples,
        "fuse_triples": fuse_triples,
        "load_local_env": load_local_env,
        "require_env": require_env,
    }

@st.cache_data(show_spinner=False)
def load_pdf_pipeline_config():
    return load_json_file(PDF_CONFIG_PATH, {})

@st.cache_data(show_spinner=False)
def load_pdf_manifest():
    manifest = load_json_file(PDF_MANIFEST_PATH, [])
    # 将 Linux 路径转为 Windows 本地路径
    fixed = []
    for item in manifest:
        payload = dict(item)
        image_path = resolve_project_path(payload.get("image_path", ""))
        source_dir = resolve_project_path(payload.get("source_dir", ""))
        payload["resolved_image_path"] = str(image_path)
        payload["resolved_source_dir"] = str(source_dir)
        payload["image_exists"] = image_path.exists()
        fixed.append(payload)
    return fixed

def build_pdf_doc_map(config, manifest):
    manifest_by_doc = {}
    for item in manifest:
        doc_name = item.get("doc_name", "未命名文档")
        manifest_by_doc.setdefault(doc_name, []).append(item)
    ordered_doc_names = []
    for doc in config.get("input_documents", []):
        doc_name = doc.get("doc_name")
        if doc_name in manifest_by_doc:
            ordered_doc_names.append(doc_name)
    for doc_name in manifest_by_doc:
        if doc_name not in ordered_doc_names:
            ordered_doc_names.append(doc_name)
    return ordered_doc_names, manifest_by_doc

def get_pdf_stage_paths(item):
    doc_dir = PDF_INTERMEDIATE_ROOT / sanitize_path_component(item.get("doc_name", "")) / item["image_id"]
    return {
        "ocr_terms": doc_dir / "ocr" / "terms.json",
        "ocr_full": doc_dir / "ocr" / "full.json",
        "ocr_text": doc_dir / "ocr" / "ocr.txt",
        "desc_result": doc_dir / "description" / "result.json",
        "desc_raw": doc_dir / "description" / "raw.txt",
        "triples_result": doc_dir / "triples" / "result.json",
        "triples_raw": doc_dir / "triples" / "raw.txt",
    }

def load_pdf_image_bundle(item):
    paths = get_pdf_stage_paths(item)
    ocr_terms_payload = load_json_file(paths["ocr_terms"], {})
    ocr_full_payload = load_json_file(paths["ocr_full"], [])
    description_payload = load_json_file(paths["desc_result"], {})
    triples_payload = load_json_file(paths["triples_result"], [])
    return {
        "paths": paths,
        "ocr_terms_payload": ocr_terms_payload,
        "ocr_terms": ocr_terms_payload.get("whitelist_terms", []),
        "ocr_full": ocr_full_payload,
        "ocr_text": load_text_file(paths["ocr_text"]),
        "description": description_payload,
        "description_raw": load_text_file(paths["desc_raw"]),
        "triples": triples_payload,
        "triples_raw": load_text_file(paths["triples_raw"]),
    }

def build_ocr_whitelist_confidence_df(ocr_terms_payload, ocr_full_payload):
    raw_terms = ocr_terms_payload.get("whitelist_terms", []) if isinstance(ocr_terms_payload, dict) else []
    score_map = {}
    for record in ocr_full_payload if isinstance(ocr_full_payload, list) else []:
        if not isinstance(record, dict):
            continue
        text = str(record.get("text", "")).strip()
        if not text:
            continue
        try:
            score = float(record.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        normalized_key = text.casefold()
        score_map.setdefault(normalized_key, []).append(score)

    rows = []
    for index, item in enumerate(raw_terms, start=1):
        if isinstance(item, dict):
            term = str(item.get("text") or item.get("term") or "").strip()
            raw_score = item.get("score", item.get("confidence", item.get("conf")))
        else:
            term = str(item).strip()
            raw_score = None

        matched_scores = score_map.get(term.casefold(), []) if term else []
        if raw_score is not None:
            try:
                confidence = float(raw_score)
            except (TypeError, ValueError):
                confidence = None
        else:
            confidence = max(matched_scores) if matched_scores else None

        rows.append(
            {
                "序号": index,
                "术语": term,
                "置信度": round(confidence, 4) if confidence is not None else None,
                "OCR命中次数": len(matched_scores),
            }
        )

    return pd.DataFrame(rows)

def format_stage_status(exists, detail):
    return "已完成" if exists else f"缺失（{detail}）"

def clear_pdf_stage_outputs(item, config):
    paths = get_pdf_stage_paths(item)
    for stage_dir in {paths["ocr_terms"].parent, paths["desc_result"].parent, paths["triples_result"].parent}:
        if stage_dir.exists():
            shutil.rmtree(stage_dir)

    output_root = PDF_PIPELINE_ROOT / config.get("output_root", "data") / "intermediate"
    image_id = item["image_id"]
    doc_id = item["doc_id"]
    legacy_specs = [
        (output_root / "ocr" / str(doc_id), [f"{image_id}_ocr_full.json", f"{image_id}_ocr_terms.json", f"{image_id}_ocr.txt"]),
        (output_root / "descriptions" / str(doc_id), [f"{image_id}_desc.json", f"{image_id}_desc_raw.txt"]),
        (output_root / "raw_triples" / str(doc_id), [f"{image_id}_triples.json", f"{image_id}_triples_raw.txt"]),
    ]
    for legacy_dir, filenames in legacy_specs:
        for filename in filenames:
            file_path = legacy_dir / filename
            if file_path.exists():
                file_path.unlink()

def export_excel_snapshot(domain_name, source_name, export_name, payload, extra_summary):
    domain_dir = ensure_dir(
        WORKBENCH_EXCEL_ROOT
        / sanitize_path_component(domain_name)
        / sanitize_path_component(Path(source_name or domain_name).stem)
    )
    timestamp = current_timestamp()
    export_path = domain_dir / f"{export_name}_{timestamp}.json"
    write_json_output(export_path, payload)
    write_json_output(domain_dir / f"{export_name}_latest.json", payload)
    summary_payload = {
        "domain_name": domain_name,
        "source_name": source_name,
        "export_name": export_name,
        "export_time": timestamp,
        **extra_summary,
    }
    write_json_output(domain_dir / "session_summary.json", summary_payload)
    return export_path

def export_pdf_image_snapshot(item, bundle, log_lines):
    timestamp = current_timestamp()
    export_dir = ensure_dir(
        WORKBENCH_PDF_ROOT
        / sanitize_path_component(item.get("doc_name", "未命名文档"))
        / sanitize_path_component(item.get("image_id", "unknown_image"))
        / timestamp
    )
    write_json_output(export_dir / "image_meta.json", item)
    copy_file_if_exists(item.get("resolved_image_path", item.get("image_path", "")), export_dir / "image" / item.get("file_name", "image"))

    ocr_dir = ensure_dir(export_dir / "ocr")
    write_json_output(ocr_dir / "terms.json", bundle.get("ocr_terms_payload", {}))
    write_json_output(ocr_dir / "full.json", bundle.get("ocr_full", []))
    if bundle.get("ocr_text"):
        write_text_output(ocr_dir / "ocr.txt", bundle.get("ocr_text", ""))

    desc_dir = ensure_dir(export_dir / "description")
    write_json_output(desc_dir / "result.json", bundle.get("description", {}))
    if bundle.get("description_raw"):
        write_text_output(desc_dir / "raw.txt", bundle.get("description_raw", ""))

    triple_dir = ensure_dir(export_dir / "triples")
    write_json_output(triple_dir / "result.json", bundle.get("triples", []))
    if bundle.get("fused_triples"):
        write_json_output(triple_dir / "fused_result.json", bundle.get("fused_triples", []))
    if bundle.get("triples_raw"):
        write_text_output(triple_dir / "raw.txt", bundle.get("triples_raw", ""))

    write_text_output(export_dir / "process_log.txt", "\n".join(log_lines))
    write_json_output(
        export_dir / "export_summary.json",
        {
            "doc_name": item.get("doc_name", ""),
            "image_id": item.get("image_id", ""),
            "file_name": item.get("file_name", ""),
            "export_time": timestamp,
            "ocr_term_count": len(bundle.get("ocr_terms", [])),
            "triple_count": len(bundle.get("triples", [])),
            "table_type": bundle.get("description", {}).get("table_type", "unknown"),
        },
    )
    return export_dir

def run_pdf_pipeline_for_item(item, progress_callback, log_callback):
    config = load_pdf_pipeline_config()
    runtime_modules = load_pdf_runtime_modules()
    runtime_modules["load_local_env"](PDF_PIPELINE_ROOT / ".env")
    runtime_modules["require_env"]("DASHSCOPE_API_KEY")

    # 用解析后的 Windows 路径替换 Linux 路径
    local_item = dict(item)
    local_item["image_path"] = local_item.get("resolved_image_path", local_item.get("image_path", ""))
    local_item["source_dir"] = local_item.get("resolved_source_dir", local_item.get("source_dir", ""))

    clear_pdf_stage_outputs(local_item, config)
    single_manifest = [local_item]
    image_id = local_item["image_id"]

    log_callback(f"[START] {image_id}")
    log_callback("[CLEAN] 已清理当前图片的 OCR / Description / Triples 缓存")

    progress_callback(5, "开始执行 OCR")
    ocr_results = runtime_modules["run_ocr"](single_manifest, config, PDF_PIPELINE_ROOT)
    ocr_terms = ocr_results.get(image_id, [])
    log_callback(f"[OCR] 完成，共抽取 {len(ocr_terms)} 个术语")

    progress_callback(45, "开始生成 Description")
    descriptions = runtime_modules["generate_descriptions"](single_manifest, config, PDF_PIPELINE_ROOT)
    description_payload = descriptions.get(image_id, {})
    log_callback(f"[DESC] 完成，table_type={description_payload.get('table_type', 'unknown')}")

    progress_callback(75, "开始抽取三元组")
    triples = runtime_modules["extract_triples"](single_manifest, config, PDF_PIPELINE_ROOT, ocr_results, descriptions)
    triple_count = len(triples.get(image_id, []))
    log_callback(f"[TRIPLE] 完成，共抽取 {triple_count} 条候选三元组")

    # ── Skill: fusion.semantic_dedup_conflict.v1 语义融合 ──
    progress_callback(85, "开始语义融合（fusion.semantic_dedup_conflict.v1）")
    try:
        fused = runtime_modules["fuse_triples"](triples, single_manifest, config, PDF_PIPELINE_ROOT)
        fused_count = len(fused)
        conflict_count = sum(1 for t in fused if t.get("conflict"))
        log_callback(f"[FUSION] 完成：候选 {triple_count} 条 → 融合后 {fused_count} 条，冲突 {conflict_count} 条")
    except Exception as exc:
        log_callback(f"[FUSION] 融合失败，保留候选三元组：{exc}")
        fused = []

    progress_callback(100, "当前图片执行完成")
    log_callback(f"[DONE] {image_id} 处理完成")
    bundle = load_pdf_image_bundle(item)
    bundle["fused_triples"] = fused
    bundle["fusion_applied"] = True
    return bundle

def build_pdf_log_lines(item, bundle):
    default_lines = [
        f"[DOC] {item.get('doc_name', '')}",
        f"[IMAGE] {item.get('image_id', '')}",
        f"[OCR] {'loaded' if bundle['paths']['ocr_terms'].exists() else 'missing'} -> {bundle['paths']['ocr_terms']}",
        f"[DESC] {'loaded' if bundle['paths']['desc_result'].exists() else 'missing'} -> {bundle['paths']['desc_result']}",
        f"[TRIPLE] {'loaded' if bundle['paths']['triples_result'].exists() else 'missing'} -> {bundle['paths']['triples_result']}",
        f"[FUSION] {'applied' if bundle.get('fusion_applied') else 'not applied'} (fused_triples: {len(bundle.get('fused_triples', []))})",
        f"[SUMMARY] OCR术语 {len(bundle.get('ocr_terms', []))} 个 / 候选三元组 {len(bundle.get('triples', []))} 条 / 融合后 {len(bundle.get('fused_triples', []))} 条",
    ]
    if st.session_state.pdf_last_run_image_id == item.get("image_id") and st.session_state.pdf_last_run_logs:
        return st.session_state.pdf_last_run_logs + [line for line in default_lines if line not in st.session_state.pdf_last_run_logs]
    return default_lines

def append_triple(triples, head, relation, tail):
    head_text = clean_cell(head)
    relation_text = clean_cell(relation)
    tail_text = clean_cell(tail)
    if head_text and relation_text and tail_text:
        triples.append((head_text, relation_text, tail_text))

def analyze_excel_template(file_name, file_bytes, domain_name):
    """调用 Qwen-Plus 分析 Excel 表结构，返回适合当前文档的抽取规则建议。"""
    import base64, os, json as _json
    try:
        import openai
        api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        if not api_key:
            return {"status": "skipped", "reason": "未配置 DASHSCOPE_API_KEY"}
        client = openai.OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=25.0,
        )
    except Exception as e:
        return {"status": "skipped", "reason": f"openai 包不可用: {e}"}

    # 读取前 2 个 sheet 的表头 + 前 5 行样例
    sheets_info = []
    try:
        xls = pd.ExcelFile(BytesIO(file_bytes))
        for sname in xls.sheet_names[:3]:
            try:
                df = pd.read_excel(BytesIO(file_bytes), sheet_name=sname, header=None, nrows=6)
            except Exception:
                df = pd.read_excel(BytesIO(file_bytes), sheet_name=sname, nrows=6)
            header_row = df.iloc[0].tolist() if not df.empty else []
            sample_rows = []
            for ri in range(1, min(len(df), 6)):
                sample_rows.append([str(v)[:80] if pd.notna(v) else "" for v in df.iloc[ri].tolist()])
            sheets_info.append({
                "sheet_name": sname,
                "header_row": [str(h)[:60] if pd.notna(h) else "" for h in header_row],
                "sample_rows": sample_rows,
                "row_count": len(df),
            })
    except Exception as e:
        return {"status": "error", "reason": f"读取 Excel 失败: {e}"}

    prompt = f"""你是汽车测试知识图谱抽取系统的规则设计专家。请分析以下 Excel 文件的结构，给出三元组抽取规则建议。

文件名: {file_name}
业务域: {domain_name}

各 Sheet 结构:
{_json.dumps(sheets_info, ensure_ascii=False, indent=2)}

请输出 JSON（只输出 JSON，不要额外文字）：
{{
  "template_type": "lock_test_case | grouped_test_case | unknown",
  "confidence": 0.0-1.0,
  "extraction_rules": {{
    "sheet_index": 0,
    "header_row_index": 0,
    "case_id_column": "列名或索引",
    "case_name_column": "列名或索引",
    "columns_to_extract": ["列1", "列2"],
    "relation_mapping": {{
      "列名": "关系名"
    }},
    "structured_fields": ["哪些列包含结构化文本需要正则拆分"],
    "notes": "其他建议"
  }}
}}"""
    try:
        resp = client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        raw = resp.choices[0].message.content.strip()
        # 提取 JSON
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        result = _json.loads(raw)
        result["status"] = "success"
        result["raw_response"] = raw[:500]
        return result
    except Exception as e:
        return {"status": "error", "reason": str(e), "raw": raw[:300] if 'raw' in dir() else ""}

def build_grouped_case_triples(group):
    first_row = group["rows"][0]
    code = first_row.get("编号", "")
    function_name = first_row.get("编号名称", "")
    title = first_row.get("标题", "")
    triples = []
    append_triple(triples, code, "编号名称", function_name)
    append_triple(triples, function_name, "包含测试用例", title)
    append_triple(triples, title, "P11L_M2", first_row.get("P11L_M2", ""))
    append_triple(triples, title, "S12L_M1", first_row.get("S12L_M1", ""))
    for row_data in group["rows"]:
        step_no = row_data.get("#", "")
        step_items = split_numbered_items(row_data.get("步骤", ""))
        expected_items = split_numbered_items(row_data.get("预期结果", ""))
        step_detail = row_data.get("步骤描述", "")
        result_signal = row_data.get("结果信号", "")
        relation = "前提条件" if step_no == "1" else "操作动作"
        for item in step_items:
            append_triple(triples, title, relation, item)
        if step_detail:
            detail_relation = "前提条件描述" if step_no == "1" else "步骤描述"
            append_triple(triples, title, detail_relation, step_detail)
        for item in expected_items:
            append_triple(triples, title, "预期结果", item)
        if result_signal:
            append_triple(triples, title, "结果信号", result_signal)
    append_triple(triples, title, "P基线", first_row.get("P基线", ""))
    append_triple(triples, title, "SOP基线", first_row.get("SOP基线", ""))
    append_triple(triples, title, "备注", first_row.get("备注", ""))
    return triples

def build_case_records(uploaded_file):
    file_name = uploaded_file.name
    domain_name = infer_domain_from_name(file_name)
    file_bytes = uploaded_file.getvalue()
    if domain_name == "离车上锁功能测试":
        df = read_table(BytesIO(file_bytes), sheet_name=0)
        case_records = []
        for idx, row in df.iterrows():
            record = '\n'.join(f"{col}: {row[col]}" for col in df.columns)
            tc = parse_test_case_string(record)
            triples = generate_triples(tc)
            case_name = tc.get("Test Case Name", "") or f"第 {idx + 1} 行"
            raw_row = {col: str(row[col]) for col in df.columns}
            case_records.append({
                "row": idx + 1,
                "case_name": case_name,
                "triples": triples,
                "raw_data": raw_row,
            })
        st.session_state.llm_analysis = None
        return domain_name, case_records, df

    # ── 分组模板：先调用 LLM 分析表格结构，生成抽取规则 ──
    llm_analysis = analyze_excel_template(uploaded_file.name, file_bytes, domain_name)
    groups = build_grouped_rows(BytesIO(file_bytes), domain_name)
    case_records = []
    for group in groups:
        first_row = group["rows"][0]
        title = clean_cell(first_row.get("标题", ""))
        function_name = clean_cell(first_row.get("编号名称", ""))
        code = clean_cell(first_row.get("编号", ""))
        case_name = title or function_name or code or f"第 {group['row']} 行"
        # 存储原始行数据供审查界面展示
        raw_cols = {}
        for rd in group["rows"]:
            for k, v in rd.items():
                if v and not k.startswith("col_"):
                    raw_cols[k] = v
        case_records.append({
            "row": group["row"],
            "case_name": case_name,
            "triples": build_grouped_case_triples(group),
            "raw_data": raw_cols,
            "raw_rows": group["rows"],
        })
    return domain_name, case_records, None, llm_analysis

def display_structured_triples(current_triples, previous_triples):
    """在一个美观的、可滚动的容器中显示分类和对比后的三元组。"""

    prev_triples_dict = {(h, r): t for h, r, t in previous_triples}

    def format_triple_line(h, r, t):
        key = (h, r)
        line = f"- ({h}, {r}, {t})"
        if key in prev_triples_dict:
            if prev_triples_dict[key] != t:
                line += " <span style='color:#FFA500; font-weight:bold;'># 值不同</span>"
        else:
            line += " <span style='color:#32CD32; font-weight:bold;'># 新增</span>"
        return line

    relation_set = {r for _, r, _ in current_triples}
    if relation_set and relation_set.isdisjoint({'属于类型', '是', '验证逻辑', '需要前提条件', '对应信号', '预期值', '需要复合条件', '执行动作', '关联信号', '动作值', '预期行为'}):
        base_defs, step_defs, result_defs = [], [], []
        for h, r, t in current_triples:
            if r in ['编号名称', '包含测试用例', 'P11L_M2', 'S12L_M1', 'P基线', 'SOP基线', '备注']:
                base_defs.append((h, r, t))
            elif r in ['前提条件', '操作动作', '前提条件描述', '步骤描述']:
                step_defs.append((h, r, t))
            else:
                result_defs.append((h, r, t))
        with st.container(height=450):
            tab1, tab2, tab3 = st.tabs(["🎯 **测试用例定义**", "📝 **步骤信息**", "⚡️ **结果信息**"])
            with tab1:
                if base_defs:
                    for h, r, t in base_defs:
                        st.markdown(format_triple_line(h, r, t), unsafe_allow_html=True)
                else:
                    st.write("无数据")
            with tab2:
                if step_defs:
                    for h, r, t in step_defs:
                        st.markdown(format_triple_line(h, r, t), unsafe_allow_html=True)
                else:
                    st.write("无数据")
            with tab3:
                if result_defs:
                    for h, r, t in result_defs:
                        st.markdown(format_triple_line(h, r, t), unsafe_allow_html=True)
                else:
                    st.write("无数据")
        return

    # --- 新的分组逻辑，严格区分前提链路下的信号与取值约束 ---
    test_case_defs, precond_defs, precond_maps, precond_vals = [], [], [], []
    action_defs, result_defs = [], []
    preconditions = {t for h, r, t in current_triples if r in ['需要前提条件', '前提条件']}
    expectations = {t for h, r, t in current_triples if r in ['预期行为', '预期结果']}
    # 收集前提条件链路下的(sig, '预期值', val)
    precond_sig_val_set = set()
    cond_sig_list = []
    for h, r, t in current_triples:
        if r == '对应信号' and h in preconditions:
            cond_sig_list.append((h, t))
    sig_val_map = {}
    for h, r, t in current_triples:
        if r == '预期值':
            sig_val_map[h] = t
    for cond, sig in cond_sig_list:
        if sig in sig_val_map:
            precond_sig_val_set.add((sig, '预期值', sig_val_map[sig]))
    for h, r, t in current_triples:
        if r in ['属于类型', '是', '验证逻辑']:
            test_case_defs.append((h, r, t))
        elif r == '需要前提条件':
            precond_defs.append((h, r, t))
        elif r == '对应信号' and h in preconditions:
            precond_maps.append((h, r, t))
        elif (h, r, t) in precond_sig_val_set:
            precond_vals.append((h, r, t))
        # 其余所有'预期值'都归为预期结果
        elif r == '预期值':
            result_defs.append((h, r, t))
        elif r in ['需要复合条件', '执行动作', '关联信号', '动作值']:
            action_defs.append((h, r, t))
        elif r == '预期行为' or (r == '对应信号' and h in expectations):
            result_defs.append((h, r, t))

    # --- 渲染界面 ---
    with st.container(height=450):
        tab1, tab2, tab3 = st.tabs(["🎯 **测试用例定义**", "📝 **前提条件**", "⚡️ **动作与结果**"])

        with tab1:
            if test_case_defs:
                for h, r, t in test_case_defs:
                    st.markdown(format_triple_line(h, r, t), unsafe_allow_html=True)
            else:
                st.write("无数据")

        with tab2:
            st.markdown("##### ➤ 条件实体定义")
            if precond_defs:
                for h, r, t in precond_defs:
                    st.markdown(format_triple_line(h, r, t), unsafe_allow_html=True)
            else:
                st.write("无数据")

            st.markdown("---")
            st.markdown("##### ➤ 条件与信号映射")
            if precond_maps:
                for h, r, t in precond_maps:
                    st.markdown(format_triple_line(h, r, t), unsafe_allow_html=True)
            else:
                st.write("无数据")

            st.markdown("---")
            st.markdown("##### ➤ 信号与取值约束")
            if precond_vals:
                for h, r, t in precond_vals:
                    st.markdown(format_triple_line(h, r, t), unsafe_allow_html=True)
            else:
                st.write("无数据")

        with tab3:
            st.markdown("##### ➤ 动作定义")
            if action_defs:
                for h, r, t in action_defs:
                    st.markdown(format_triple_line(h, r, t), unsafe_allow_html=True)
            else:
                st.write("无数据")

            st.markdown("---")
            st.markdown("##### ➤ 预期结果")
            if result_defs:
                for h, r, t in result_defs:
                    st.markdown(format_triple_line(h, r, t), unsafe_allow_html=True)
            else:
                st.write("无数据")


def categorize_nodes(triples: list) -> dict:
    """通过三步分析法，预处理所有三元组，为每个节点精确分配类别。"""
    node_categories = {}

    # Step 1: Identify primary entities to build context
    preconditions = {t for h, r, t in triples if r in ['需要前提条件', '前提条件']}
    expectations = {t for h, r, t in triples if r in ['预期行为', '预期结果']}
    actions = {t for h, r, t in triples if r in ['执行动作', '操作动作']}
    composites = {h for h, r, t in triples if r == '执行动作'}
    test_cases = {h for h, r, t in triples if r in ['是', '需要前提条件', '预期行为', '前提条件', '操作动作', '预期结果', '前提条件描述', '步骤描述', 'P基线', 'SOP基线', '备注']}

    # Step 2: Assign categories to primary entities
    for node_set, category in [
        (test_cases, "Test Case"),
        (composites, "Composite"),
        (preconditions, "Precondition"),
        (expectations, "Expectation"),
        (actions, "Action")
    ]:
        for node in node_set:
            # Avoid overwriting a more specific category
            if node not in node_categories:
                node_categories[node] = category

    # Step 3: Assign categories to dependent signals and values
    for h, r, t in triples:
        head_category = node_categories.get(h)
        if r == "对应信号":
            if head_category == "Precondition":
                node_categories[t] = "Precond Signal"
            elif head_category == "Expectation":
                node_categories[t] = "Expect Signal"
        elif r == "关联信号" and head_category == "Action":
            node_categories[t] = "Action Signal"
        elif r == "预期值":
            if head_category == "Precond Signal":
                node_categories[t] = "Precond Value"
            elif head_category == "Expect Signal":
                node_categories[t] = "Expect Value"
        elif r == "动作值":
            node_categories[t] = "Action Value"

    return node_categories

def build_graph_visuals(all_triples, last_added_triples, search_term="", highlight_cases=[], display_mode="Full Graph"):
    """构建用于 agraph 的节点和边对象列表，处理高亮逻辑"""
    nodes = []
    edges = []

    # --- Accurate Node Categorization ---
    node_categories = categorize_nodes(all_triples)

    # --- Search, Highlight & Focus Logic ---
    highlight_nodes = set()
    is_highlight_active = bool(search_term or highlight_cases)

    # Determine the triples to be displayed based on the mode
    displayed_triples = all_triples

    if highlight_cases:
        for case_name in highlight_cases:
            # A more robust implementation would trace all paths from the case name.
            related_triples = [t for t in all_triples if t[0] == case_name]
            for h, r, t in related_triples:
                # Basic path finding
                highlight_nodes.add(h)
                highlight_nodes.add(t)
                for h2,r2,t2 in all_triples:
                    if h2 == t:
                         highlight_nodes.add(t2)

        if display_mode == "Focus on Selected":
            displayed_triples = [triple for triple in all_triples if triple[0] in highlight_nodes and triple[2] in highlight_nodes]

    elif search_term:
        highlight_nodes.add(search_term)
        for h, r, t in all_triples:
            if h == search_term:
                highlight_nodes.add(t)
            if t == search_term:
                highlight_nodes.add(h)

    last_added_nodes = {item for triple in last_added_triples for item in (triple[0], triple[2])}

    # --- Node Creation from displayed triples ---
    node_ids = {item for triple in displayed_triples for item in (triple[0], triple[2])}
    for node_id in node_ids:
        is_new = node_id in last_added_nodes
        is_highlighted = node_id in highlight_nodes

        # Determine Color
        if is_highlight_active:
            if is_highlighted:
                category = node_categories.get(node_id, "Default")
                color = CATEGORY_STYLES.get(category, {}).get("color", "#1E90FF")
            else:
                color = CATEGORY_STYLES["GrayedOut"]["color"]
        elif is_new:
            color = CATEGORY_STYLES["Test Case"]["color"] # Bright yellow for new
        else:
            color = CATEGORY_STYLES["Default"]["color"] # Default blue

        # Determine Size
        size = 25 if is_highlight_active and (node_id == search_term or node_id in highlight_cases) else 15

        nodes.append(Node(id=node_id, label=node_id, size=size, color=color))

    # --- Edge Creation from displayed triples ---
    for h, r, t in displayed_triples:
        color = "#C0C0C0" if is_highlight_active and (h not in highlight_nodes or t not in highlight_nodes) else "#999"
        edges.append(Edge(source=h, target=t, label=r, color=color))

    return nodes, edges



def llm_reextract_row(row_data: dict, domain_name: str, existing_triples: list = None) -> list:
    """[deprecated] use llm_reextract_row_v2 instead"""
    return llm_reextract_row_v2(row_data, domain_name, "", existing_triples)


def llm_reextract_row_v2(row_data: dict, domain_name: str, improvement_hint: str = "", existing_triples: list = None) -> list:
    """调用 Qwen-Plus 对单行原始数据重新抽取三元组，支持改进方向指导。返回[(head, relation, tail), ...]"""
    import os, json as _json
    try:
        from openai import OpenAI
        api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        if not api_key:
            return []
        client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", timeout=45.0)
    except Exception:
        return []

    raw_text = "\n".join(f"{k}: {v}" for k, v in row_data.items() if v and not str(k).startswith("col_"))
    existing_hint = ""
    if existing_triples:
        existing_hint = "\n当前已抽取的三元组（供参考）：\n" + "\n".join(
            [f"  ({h}, {r}, {t})" for h, r, t in (existing_triples or [])[:20]]
        )
    improvement_section = ""
    if improvement_hint and improvement_hint.strip():
        improvement_section = f"\n【重要】工程师改进方向：{improvement_hint}\n请严格按照上述改进方向调整抽取策略。"

    prompt = f"""你是汽车测试知识图谱抽取专家。请从以下测试用例行数据中抽取(head, relation, tail)三元组。

业务域: {domain_name}

原始行数据:
{raw_text}
{existing_hint}
{improvement_section}

规则:
1. head/tail 使用原文中的精确术语，不要缩写
2. relation 使用简洁中文
3. 每个列的值如果包含多条，每条单独出三元组
4. 如果工程师提供了改进方向，务必遵循
5. 只输出 JSON 数组，不要其他文字

输出格式:
[{{"head": "...", "relation": "...", "tail": "..."}}, ...]"""

    try:
        resp = client.chat.completions.create(
            model="qwen-plus", messages=[{"role": "user", "content": prompt}], temperature=0.05
        )
        raw = resp.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip() if "```json" in raw else raw.split("```")[1].split("```")[0].strip()
        result = _json.loads(raw)
        return [(item["head"], item["relation"], item["tail"]) for item in result if item.get("head") and item.get("relation") and item.get("tail")]
    except Exception:
        return None

def render_excel_workbench():
    render_hero_banner(
        "Excel 图谱工作台",
        "面向测试用例 Excel 的逐行三元组抽取与图谱构建。适合做人工校验、差异观察和结构化导出。",
        "📗",
        align="left",
        compact=True,
    )
    control_col, content_col = st.columns([0.85, 2.15])

    with control_col:
        render_section_header("控制面板", "上传 Excel、推进抽取流程，并按案例高亮或导出。")
        uploaded_file = st.file_uploader("上传 Excel 文件", type=["xlsx"], key="excel_file_uploader")

        if uploaded_file and st.session_state.uploaded_file_name != uploaded_file.name:
            try:
                reset_state()
                result = build_case_records(uploaded_file)
                domain_name, case_records = result[0], result[1]
                df = result[2] if len(result) > 2 else None
                llm_analysis = result[3] if len(result) > 3 else None
                st.session_state.domain_name = domain_name
                st.session_state.case_records = case_records
                st.session_state.df = df
                st.session_state.uploaded_file_name = uploaded_file.name
                st.session_state.current_row = -1
            except Exception as exc:
                reset_state()
                st.error(f"文件解析失败：{exc}")

        if st.session_state.case_records is None:
            st.info("请先上传一个 Excel 文件。")
            return

        total_rows = len(st.session_state.case_records)
        # ── 业务指标 ──
        metric_a, metric_b, metric_c = st.columns(3)
        with metric_a:
            render_metric_card("业务领域", st.session_state.domain_name, "自动识别", tone="blue")
        with metric_b:
            render_metric_card("案例总数", total_rows, "待逐行审阅", tone="purple")
        reviewed_count = len(st.session_state.excel_reviewed_rows)
        with metric_c:
            render_metric_card("已确认", f"{reviewed_count}/{total_rows}", f"累计 {len(st.session_state.all_edges)} 条三元组", tone="green" if reviewed_count > 0 else "amber")

        # ── Skill 路由决策 ──
        excel_skill = match_excel_skill(st.session_state.domain_name)
        if excel_skill:
            with st.expander("🧠 Skill 路由决策", expanded=True):
                render_skill_card(excel_skill, matched=True)
        else:
            with st.expander("🧠 Skill 路由决策", expanded=True):
                st.warning(f"未找到匹配的 Skill（领域：{st.session_state.domain_name}）。使用确定性规则抽取。")

        # ── LLM 表结构分析 ──
        if hasattr(st.session_state, "llm_analysis") and st.session_state.llm_analysis:
            analysis = st.session_state.llm_analysis
            if analysis.get("status") == "success":
                with st.expander("🤖 LLM 表结构分析（参考）", expanded=False):
                    rules = analysis.get("extraction_rules", {})
                    template_type = analysis.get("template_type", "unknown")
                    confidence = analysis.get("confidence", 0)
                    st.caption(f"识别类型: {template_type} (置信度 {confidence:.0%})")
                    if rules.get("columns_to_extract"):
                        columns = ", ".join(rules["columns_to_extract"][:8])
                        st.caption(f"建议抽取列: {columns}")
                    if rules.get("relation_mapping"):
                        for col, rel in list(rules["relation_mapping"].items())[:8]:
                            st.caption(f"  {col} → {rel}")
                    if rules.get("notes"):
                        st.info(rules["notes"])
            elif analysis.get("status") == "error":
                st.caption(f"LLM 分析失败: {analysis.get('reason', '')[:120]}")

            # ── 自进化：LLM 分析发现新模板时，自动沉淀 pending Skill ──
            if analysis.get("status") == "success" and not excel_skill:
                from datetime import datetime as _dt
                ttype = analysis.get("template_type", "unknown")
                if ttype not in ("lock_test_case", "grouped_test_case", "unknown"):
                    draft_id = f"excel.{ttype}.draft"
                    ppath = PENDING_SKILLS_ROOT / f"{draft_id}.SKILL.md"
                    if not ppath.exists():
                        ppath.parent.mkdir(parents=True, exist_ok=True)
                        rules = analysis.get("extraction_rules", {})
                        draft = f"""# Pending Skill: {ttype}
- skill_id: {draft_id}
- source: {st.session_state.uploaded_file_name}
- domain: {st.session_state.domain_name}
- confidence: {analysis.get("confidence", 0)}
- created: {_dt.now().strftime("%Y-%m-%d %H:%M:%S")}

## LLM Extraction Rules
- template_type: {ttype}
- columns: {json.dumps(rules.get("columns_to_extract", []), ensure_ascii=False)}
- mapping:
{chr(10).join(f"  {k} -> {v}" for k,v in rules.get("relation_mapping", {}).items())}
- notes: {rules.get("notes", "")}

## Raw LLM Response
{analysis.get("raw_response", "N/A")[:2000]}
"""
                        ppath.write_text(draft, encoding="utf-8")
                        if 'pending_skills_created' not in st.session_state:
                            st.session_state.pending_skills_created = []
                        st.session_state.pending_skills_created.append(str(ppath))
                    st.info(f"新 Skill 草稿已生成: {ppath.name}")

            # ── 原始行数据（始终展示当前行）──
            if st.session_state.current_row >= 0:
                row_info_preview = st.session_state.case_records[st.session_state.current_row]
                with st.expander("原始行数据 (对照) —— 行 " + str(row_info_preview.get("row", "")), expanded=True):
                    raw = row_info_preview.get("raw_data", {})
                    if raw:
                        raw_df = pd.DataFrame([
                            {"列名": str(k)[:30], "值": str(v)[:400] if v else "(空)"}
                            for k, v in raw.items() if k and not str(k).startswith("col_")
                        ])
                        st.dataframe(raw_df, width="stretch", hide_index=True, height=300,
                                     column_config={"列名": st.column_config.TextColumn(width="small"),
                                                    "值": st.column_config.TextColumn(width="large")})
                    else:
                        st.caption("当前行无结构化原始数据")
            else:
                st.caption("上传文件并点击「下一行」后显示原始数据。")

        # ── 进度 + 导航 ──
        st.progress((st.session_state.current_row + 1) / total_rows,
                     text=f"审阅进度: {st.session_state.current_row + 1} / {total_rows}")

        nav_cols = st.columns([1.4, 1])
        with nav_cols[0]:
            if st.session_state.current_row < total_rows - 1:
                if st.button("⏭️ 下一行", width="stretch", key="excel_next_row", type="primary"):
                    st.session_state.current_row += 1
                    st.session_state.previous_triples = st.session_state.last_added_triples
                    new_triples = st.session_state.case_records[st.session_state.current_row]["triples"]
                    st.session_state.last_added_triples = new_triples
                    st.session_state.all_edges.extend(new_triples)
                    if hasattr(st.session_state, "llm_reextracted"):
                        st.session_state.llm_reextracted = None
                    st.rerun()
            else:
                st.success("✅ 所有行处理完毕")
        with nav_cols[1]:
            if st.button("🔄 重置", width="stretch", key="excel_reset"):
                reset_state()
                st.rerun()
    with content_col:
        review_tab, graph_tab, export_tab = st.tabs(["\U0001f4dd 抽取审阅", "\U0001f517 知识图谱", "\U0001f4e5 导出归档"])

        # ── Tab 1: 抽取审阅 ──
        with review_tab:
            if st.session_state.current_row == -1:
                st.info("请先在左侧控制面板上传文件，然后点击「下一行」开始逐行审阅。")
            else:
                row_info = st.session_state.case_records[st.session_state.current_row]
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("行号", row_info["row"])
                cname = row_info.get("case_name", "")
                c2.metric("案例", cname[:18] + (".." if len(cname) > 18 else ""))
                c3.metric("域", st.session_state.domain_name[:8])
                reviewed_label = "已确认" if st.session_state.current_row in st.session_state.excel_reviewed_rows else "待审"
                c4.metric("状态", reviewed_label)
                c5.metric("三元组", len(st.session_state.last_added_triples))
                # ── 双栏布局：编辑表格 + 原始行数据对照 ──
                edit_col, raw_col = st.columns([1.3, 1])
                with edit_col:
                    with st.container(height=520):
                        reviewed_triples, review_summary = render_triple_review_editor(
                            "工程师校验区",
                            "可直接改写 head / relation / tail；取消勾选的行不保存。",
                            st.session_state.last_added_triples,
                            key=f"excel_review_editor_{st.session_state.current_row}",
                            output_format="tuple",
                        )
                with raw_col:
                    with st.container(height=520):
                        st.markdown("##### 原始行数据 (对照)")
                        raw = row_info.get("raw_data", {})
                        if raw:
                            raw_df = pd.DataFrame([
                                {"列名": str(k)[:30], "值": str(v)[:300] if v else "(空)"}
                                for k, v in raw.items() if k and not str(k).startswith("col_")
                            ])
                            st.dataframe(raw_df, width="stretch", hide_index=True, height=410,
                                         column_config={"列名": st.column_config.TextColumn(width="small"),
                                                        "值": st.column_config.TextColumn(width="large")})
                        else:
                            st.caption("无原始数据")

                # ── 操作按钮 ──
                btn1, btn2, btn3, btn4 = st.columns([1.2, 0.8, 1.2, 1.5])
                with btn1:
                    if st.button("确认保存当前行", width="stretch", key=f"excel_save_review_{st.session_state.current_row}", type="primary"):
                        row_info["triples"] = reviewed_triples
                        st.session_state.last_added_triples = reviewed_triples
                        if st.session_state.current_row not in st.session_state.excel_reviewed_rows:
                            st.session_state.all_edges.extend(reviewed_triples)
                            st.session_state.excel_reviewed_rows.append(st.session_state.current_row)
                        review_path = save_excel_case_review(st.session_state.domain_name, st.session_state.uploaded_file_name, row_info, reviewed_triples, review_summary)
                        st.session_state.excel_last_review_path = str(review_path)
                        st.success("已保存")
                with btn2:
                    if st.button("跳过", width="stretch", key=f"excel_skip_{st.session_state.current_row}"):
                        st.session_state.current_row += 1
                        st.rerun()
                with btn3:
                    llm_clicked = st.button("LLM 重新抽取", width="stretch", key=f"excel_llm_reextract_{st.session_state.current_row}")
                with btn4:
                    if hasattr(st.session_state, "llm_reextracted") and st.session_state.llm_reextracted:
                        st.info(f"当前为 LLM 重抽结果，{len(st.session_state.last_added_triples)} 条。")

                # ── LLM 重新抽取（带改进方向输入）──
                if llm_clicked:
                    st.markdown("---")
                    st.caption("输入改进方向，LLM 基于原始行数据重新抽取。")
                    improvement_hint = st.text_area(
                        "改进方向 / 具体要求",
                        placeholder="如：请把 Relation 改为英文术语、请从 Actions 列中拆分出单独的步骤三元组、请将信号值也单独列出...",
                        key=f"excel_llm_hint_{st.session_state.current_row}",
                        height=80,
                    )
                    if st.button("执行 LLM 抽取", width="stretch", key=f"excel_llm_run_{st.session_state.current_row}", type="primary"):
                        with st.spinner("Qwen-Plus 正在根据改进方向重新抽取..."):
                            raw_data = row_info.get("raw_data", {})
                            llm_result = llm_reextract_row_v2(raw_data, st.session_state.domain_name, improvement_hint, reviewed_triples)
                            if llm_result is None:
                                st.error("LLM 调用失败，请检查 API Key 和网络。")
                            elif len(llm_result) == 0:
                                st.warning("LLM 未产生结果，请调整改进方向后重试。")
                            else:
                                st.session_state.last_added_triples = llm_result
                                st.session_state.llm_reextracted = True
                                st.success(f"LLM 重抽完成：{len(llm_result)} 条三元组。请审阅后确认保存。")
                                st.rerun()

                with st.expander("分组视图（快速阅读）", expanded=False):
                    display_structured_triples(reviewed_triples, st.session_state.previous_triples)

        # ── Tab 2: 知识图谱 ──
        with graph_tab:
            if not st.session_state.all_edges:
                st.info("图谱为空。请在「抽取审阅」中逐行确认三元组，确认后会自动进入累计图谱。")
            else:
                with st.expander("高亮设置", expanded=False):
                    hl_col1, hl_col2 = st.columns(2)
                    with hl_col1:
                        all_node_ids = sorted(list({item for triple in st.session_state.all_edges for item in (triple[0], str(triple[2]))}))
                        selected_search = st.selectbox("选择节点高亮路径", options=[""] + all_node_ids, key="graph_hl_node")
                        if selected_search:
                            st.session_state.search_term = selected_search
                    with hl_col2:
                        test_case_names = sorted({record["case_name"] for record in st.session_state.case_records})
                        selected_cases = st.multiselect("选择测试用例高亮", options=test_case_names, key="graph_hl_cases")
                        if selected_cases:
                            st.session_state.highlight_cases = selected_cases
                            st.session_state.display_mode = "Focus on Selected"

                nodes, edges = build_graph_visuals(
                    st.session_state.all_edges, st.session_state.last_added_triples,
                    st.session_state.search_term, st.session_state.highlight_cases, st.session_state.display_mode
                )
                config = Config(width=900, height=650, directed=True, physics=True, hierarchical=False,
                                nodeHighlightBehavior=True, highlightColor="#F6E05E")
                try:
                    agraph(nodes=nodes, edges=edges, config=config)
                except Exception:
                    st.warning("图谱渲染失败（streamlit-agraph 兼容问题），不影响其他功能。")

        # ── Tab 3: 导出归档 ──
        with export_tab:
            render_section_header("导出与归档", "归档已验证的三元组或导出全部/选中案例。")
            e1, e2 = st.columns(2)
            with e1:
                if st.button("全部三元组 JSON 归档", width='stretch', key="excel_archive_all"):
                    all_triples_data = []
                    for record in st.session_state.case_records:
                        for h, r, t in record["triples"]:
                            all_triples_data.append({'row': record["row"], 'head': h, 'relation': r, 'tail': t})
                    archive_path = export_excel_snapshot(
                        st.session_state.domain_name, st.session_state.uploaded_file_name,
                        "all_triples", all_triples_data,
                        {"record_count": len(all_triples_data), "case_count": len(st.session_state.case_records)},
                    )
                    st.session_state.excel_last_export_path = str(archive_path)
                    st.success(f"已归档：{archive_path}")

                all_triples_data = []
                for record in st.session_state.case_records:
                    for h, r, t in record["triples"]:
                        all_triples_data.append({'row': record["row"], 'head': h, 'relation': r, 'tail': t})
                st.download_button("下载全部三元组 JSON", data=json.dumps(all_triples_data, ensure_ascii=False, indent=4),
                                   file_name='triples_output.json', mime='application/json', width='stretch', key="excel_dl_all")

            with e2:
                hl_cases = st.session_state.get("highlight_cases", [])
                if hl_cases:
                    export_triples = []
                    for case_name in hl_cases:
                        for record in st.session_state.case_records:
                            if record["case_name"] == case_name:
                                for h, r, t in record["triples"]:
                                    export_triples.append({'test_case': case_name, 'head': h, 'relation': r, 'tail': t})
                    selected_json = json.dumps(export_triples, ensure_ascii=False, indent=4)
                    if st.button(f"归档高亮案例 ({len(hl_cases)})", width='stretch', key="excel_archive_hl"):
                        archive_path = export_excel_snapshot(
                            st.session_state.domain_name, st.session_state.uploaded_file_name,
                            "selected_cases", export_triples,
                            {"selected_case_count": len(hl_cases), "record_count": len(export_triples)},
                        )
                        st.success(f"已归档：{archive_path}")
                    st.download_button(f"下载高亮案例 ({len(hl_cases)})", data=selected_json,
                                       file_name='selected_test_cases.json', mime='application/json', width='stretch', key="excel_dl_hl")
                else:
                    st.info("在「知识图谱」Tab 中勾选测试用例后，可在此导出选中案例。")

            if st.session_state.excel_last_export_path:
                st.caption(f"最近归档：{st.session_state.excel_last_export_path}")

            with st.expander("审核历史", expanded=False):
                reviewed_dir = WORKBENCH_EXCEL_ROOT / sanitize_path_component(st.session_state.domain_name) / sanitize_path_component(Path(st.session_state.uploaded_file_name or "upload").stem) / "reviewed_cases"
                if reviewed_dir.exists():
                    reviewed_files = sorted(reviewed_dir.glob("*.json"), reverse=True)[:10]
                    if reviewed_files:
                        for rf in reviewed_files:
                            st.caption(rf.name)
                    else:
                        st.caption("暂无审核记录。")
                else:
                    st.caption("暂无审核记录。")


def render_pdf_description(description_payload, description_raw):
    if not description_payload:
        st.warning("当前图片暂无 description 结果。")
        return

    render_kv_panel([
        ("主题", description_payload.get("topic", "无")),
        ("行语义", description_payload.get("row_semantics", "无")),
        ("列语义", description_payload.get("column_semantics", "无")),
    ], tone="blue")

    list_fields = [
        ("核心实体", description_payload.get("core_entities", [])),
        ("核心条件", description_payload.get("core_conditions", [])),
        ("核心输出", description_payload.get("core_outputs", [])),
        ("核心故障", description_payload.get("core_faults", [])),
        ("时序约束", description_payload.get("core_timing_constraints", [])),
        ("不确定点", description_payload.get("uncertain_points", [])),
    ]
    for title, values in list_fields:
        render_chip_group(title, values, tone="purple" if title == "不确定点" else "blue")

    render_section_header("工程解释", "模型对该表格的工程语义概括。")
    st.markdown(f"> {description_payload.get('engineering_interpretation', '无')}")

    with st.expander("查看原始 description 结果"):
        st.json(description_payload)
        if description_raw:
            st.code(description_raw, language="json")


def render_pdf_triples(triples_payload, triples_raw):
    if not triples_payload:
        st.warning("当前图片暂无候选三元组。")
        return

    relation_counter = Counter(item.get("relation", "未知关系") for item in triples_payload)
    render_chip_group("关系分布", [f"{key} × {value}" for key, value in relation_counter.items()], tone="green")
    triples_df = pd.DataFrame(triples_payload)
    display_columns = [col for col in ["head", "relation", "tail", "triple_type", "confidence_note"] if col in triples_df.columns]
    st.dataframe(triples_df[display_columns], width='stretch', hide_index=True)

    with st.expander("查看原始三元组结果"):
        st.json(triples_payload)
        if triples_raw:
            st.code(triples_raw, language="json")



def llm_reextract_pdf(context: dict, existing_review: list = None) -> list:
    """[deprecated] use llm_reextract_pdf_v2 instead"""
    return llm_reextract_pdf_v2(context, "", existing_review)


def llm_reextract_pdf_v2(context: dict, improvement_hint: str = "", existing_review: list = None) -> list:
    """调用 Qwen-Plus 根据 OCR + 描述 + 已有三元组重新抽取。返回 [{head,relation,tail,...}, ...]"""
    import os, json as _json
    try:
        from openai import OpenAI
        api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        if not api_key: return []
        client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", timeout=30.0)
    except Exception:
        return None

    # ── 构建 prompt ──
    improvement_section = ""
    if improvement_hint and improvement_hint.strip():
        improvement_section = f"""\n【重要】工程师改进方向：{improvement_hint}
请严格按照上述改进方向调整。如果工程师要求某列改成英文，只改那一列，其他列保持原语言不变。
如果工程师要求修改关系（relation），只改 relation 列。
如果工程师要求修改实体（head/tail），只改 head/tail 列。"""

    selected_triples_text = ""
    if context.get("selected_triples"):
        selected_triples_text = "\n需要改写 以下三元组（仅改写这些，其他保持不变）：\n" + "\n".join(
            [f"  ({t['head']}, {t['relation']}, {t['tail']})" for t in context["selected_triples"]]
        )

    prompt = f"""你是汽车技术规范知识图谱抽取专家。以下是 OCR 结果、表格描述和已有候选三元组。

表格类型: {context.get("table_type", "unknown")}
主题: {context.get("topic", "")}
核心实体: {_json.dumps(context.get("core_entities", []), ensure_ascii=False)}
工程解释: {context.get("engineering_interpretation", "")}
OCR 术语: {_json.dumps(context.get("ocr_terms", []), ensure_ascii=False)}
已有候选: {_json.dumps(context.get("existing_triples", []), ensure_ascii=False)}
{selected_triples_text}
{improvement_section}

规则:
1. head/tail 和 relation 的语言风格默认与原始 OCR 一致，不要缩写
2. 如果工程师指定了某一列的语言，只改那一列，其他列保持原样
3. 每个三元组需有 evidence_term（引用 OCR 中的具体术语）
4. 只输出 JSON 数组，不要其他文字

输出格式:
[{{\"head\": \"...\", \"relation\": \"...\", \"tail\": \"...\", \"evidence_term\": \"...\"}}, ...]"""

    try:
        resp = client.chat.completions.create(model="qwen-plus", messages=[{"role":"user","content":prompt}], temperature=0.05)
        raw = resp.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip() if "```json" in raw else raw.split("```")[1].split("```")[0].strip()
        return _json.loads(raw)
    except Exception:
        return None


def llm_fix_triple_issue(image_id: str, doc_name: str, issue: dict, all_triples: list,
                         ocr_terms: list, description: dict) -> list:
    """根据评估反馈逐条修复三元组。只修改 issue.triple_indices 中指定的行,其余保持不变。"""
    import os, json as _json
    try:
        from openai import OpenAI
        api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        if not api_key: return None
        client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", timeout=45.0)
    except Exception:
        return None

    indices = issue.get("triple_indices", [])
    affected = []
    for idx in indices:
        if 0 <= idx < len(all_triples):
            t = all_triples[idx]
            affected.append({"index": idx, "head": t.get("head",""), "relation": t.get("relation",""), "tail": t.get("tail","")})

    all_numbered = []
    for i, t in enumerate(all_triples):
        all_numbered.append({"index": i, "head": t.get("head",""), "relation": t.get("relation",""), "tail": t.get("tail","")})

    desc_brief = {"table_type": description.get("table_type",""), "topic": description.get("topic",""),
                  "engineering_interpretation": description.get("engineering_interpretation","")}

    prompt = f"""你是汽车技术规范知识图谱的修复专家。评估系统发现以下问题，请只修复受影响的三元组。

文档: {doc_name}
图片: {image_id}
表格类型: {desc_brief.get('table_type','unknown')}
主题: {desc_brief.get('topic','')}

OCR 术语参考:
{_json.dumps(ocr_terms[:50], ensure_ascii=False)}

=== 问题描述 ===
类型: {issue.get('issue_type','unknown')}
严重程度: {issue.get('severity','minor')}
描述: {issue.get('description','')}
修复建议: {issue.get('suggested_correction','')}

=== 受影响的当前三元组 ===
{_json.dumps(affected, ensure_ascii=False, indent=2)}

=== 所有三元组（供上下文参考，但只修改 affected 中的行）===
{_json.dumps(all_numbered, ensure_ascii=False, indent=2)}

=== 指令 ===
1. 只修改 issue 中指定的三元组索引（triple_indices），其余三元组保持原样
2. 如果有缺失的三元组（missing_triple），在原位置插入新三元组
3. 如果是 wrong_entity/wrong_relation，只修改错误的部分
4. 如果是 spelling，修正拼写
5. 修改后返回完整的、与原始顺序一致的三元组列表
6. 只输出 JSON 数组，不要其他文字

输出格式:
[{{"head": "...", "relation": "...", "tail": "..."}}, ...]"""

    try:
        resp = client.chat.completions.create(model="qwen-plus", messages=[{"role":"user","content":prompt}], temperature=0.03)
        raw = resp.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip() if "```json" in raw else raw.split("```")[1].split("```")[0].strip()
        result = _json.loads(raw)
        return [{"head": item["head"], "relation": item["relation"], "tail": item["tail"]} for item in result
                if item.get("head") and item.get("relation") and item.get("tail")]
    except Exception:
        return None


def render_pdf_workbench():
    render_hero_banner(
        "PDF 知识图谱构建工作台",
        "对 PDF 拆图结果进行 OCR、结构理解和三元组抽取审阅，也支持直接在线重跑当前图片。",
        "📘",
        align="left",
        compact=True,
    )

    if not PDF_PIPELINE_ROOT.exists():
        st.error(f"未找到 PDF KG Pipeline 目录：{PDF_PIPELINE_ROOT}")
        return

    config = load_pdf_pipeline_config()
    manifest = load_pdf_manifest()

    if not manifest:
        st.warning("未找到 PDF 图片清单，请先确认 pdf_pipeline 已生成 image_manifest.json。")
        return

    ordered_doc_names, manifest_by_doc = build_pdf_doc_map(config, manifest)
    if not ordered_doc_names:
        st.warning("当前 manifest 中没有可展示的文档。")
        return

    if st.session_state.pdf_doc_name not in ordered_doc_names:
        st.session_state.pdf_doc_name = ordered_doc_names[0]
        st.session_state.pdf_image_index = 0

    # ── PDF Skill 路由展示 ──
    extract_skill = match_pdf_extraction_skill()
    fusion_skill = match_pdf_fusion_skill()
    sk1, sk2 = st.columns(2)
    with sk1:
        if extract_skill:
            render_skill_card(extract_skill, matched=True)
    with sk2:
        if fusion_skill:
            render_skill_card(fusion_skill, matched=True)

    control_row1_col1, control_row1_col2, control_row1_col3, control_row1_col4 = st.columns([2.3, 1.25, 1.2, 1.05])

    with control_row1_col1:
        st.caption("规范文档")
        selected_doc_name = st.selectbox(
            "选择规范文档",
            options=ordered_doc_names,
            index=ordered_doc_names.index(st.session_state.pdf_doc_name),
            key="pdf_doc_name_select",
            label_visibility="collapsed",
        )

    if selected_doc_name != st.session_state.pdf_doc_name:
        st.session_state.pdf_doc_name = selected_doc_name
        st.session_state.pdf_image_index = 0
        st.session_state.pdf_results_visible = False
        st.session_state.pdf_loaded_result_key = ""

    doc_items = manifest_by_doc.get(st.session_state.pdf_doc_name, [])
    if not doc_items:
        st.warning("当前文档没有图片记录。")
        return

    with control_row1_col2:
        st.caption("搜索图片")
        search_text = st.text_input("搜索图片", value="", key="pdf_search_text", label_visibility="collapsed")
    with control_row1_col3:
        st.caption("结果筛选")
        only_with_triples = st.toggle("仅显示已有三元组结果的图片", value=False, key="pdf_only_with_triples", label_visibility="collapsed")
    with control_row1_col4:
        st.caption("缓存")
        if st.button("刷新 PDF 缓存", width='stretch', key="pdf_refresh_cache"):
            append_operation_history("pdf_operation_history", "pdf_operation_text_logs", "刷新 PDF 缓存", [f"文档：{st.session_state.pdf_doc_name or '当前文档'}"])
            load_pdf_pipeline_config.clear()
            load_pdf_manifest.clear()
            st.rerun()

    filtered_items = []
    for item in doc_items:
        if search_text and search_text.lower() not in item.get("image_id", "").lower() and search_text.lower() not in item.get("file_name", "").lower():
            continue
        if only_with_triples:
            if not get_pdf_stage_paths(item)["triples_result"].exists():
                continue
        filtered_items.append(item)

    if not filtered_items:
        st.warning("筛选后没有可展示的图片。")
        return

    if st.session_state.pdf_image_index >= len(filtered_items):
        st.session_state.pdf_image_index = 0

    nav_col1, nav_col2, nav_col3 = st.columns([1.1, 3.2, 1.1])
    with nav_col1:
        st.caption("图片导航")
        if st.button("⬅️ 上一张", width='stretch', key="pdf_prev_image"):
            st.session_state.pdf_image_index = max(0, st.session_state.pdf_image_index - 1)
            st.session_state.pdf_results_visible = False
            st.session_state.pdf_loaded_result_key = ""
    image_options = [f"{item['image_id']} | {item['file_name']}" for item in filtered_items]
    with nav_col2:
        st.caption("选择图片")
        selected_image_label = st.selectbox(
            "选择图片",
            options=image_options,
            index=st.session_state.pdf_image_index,
            key="pdf_image_select",
            label_visibility="collapsed",
        )
    selected_image_index = image_options.index(selected_image_label)
    if selected_image_index != st.session_state.pdf_image_index:
        st.session_state.pdf_image_index = selected_image_index
        st.session_state.pdf_results_visible = False
        st.session_state.pdf_loaded_result_key = ""
    with nav_col3:
        st.caption("图片导航")
        if st.button("下一张 ➡️", width='stretch', key="pdf_next_image"):
            st.session_state.pdf_image_index = min(len(filtered_items) - 1, st.session_state.pdf_image_index + 1)
            st.session_state.pdf_results_visible = False
            st.session_state.pdf_loaded_result_key = ""

    current_item = filtered_items[st.session_state.pdf_image_index]
    current_result_key = f"{current_item.get('doc_name', '')}::{current_item.get('image_id', '')}"
    bundle = load_pdf_image_bundle(current_item)
    description_payload = bundle["description"]
    triples_payload = bundle["triples"]
    ocr_terms = bundle["ocr_terms"]
    current_log_lines = build_pdf_log_lines(current_item, bundle)

    action_col1, action_col2, action_col3, action_col4 = st.columns([1.05, 1.15, 1.15, 2.15])
    with action_col1:
        if st.button("查看当前图片结果", width='stretch', key="pdf_show_current"):
            st.session_state.pdf_results_visible = True
            st.session_state.pdf_loaded_result_key = current_result_key
            append_operation_history(
                "pdf_operation_history",
                "pdf_operation_text_logs",
                "查看当前图片结果",
                [f"图片：{current_item.get('image_id', '无')}", f"文件：{current_item.get('file_name', '无')}"]
            )
    with action_col2:
        if st.button("▶️ 在线运行当前图片", width='stretch', key="pdf_run_current"):
            progress_holder = st.progress(0, text="准备执行当前图片")
            status_holder = st.empty()
            runtime_logs = []

            def _progress_callback(percent, text):
                progress_holder.progress(int(percent), text=text)
                status_holder.info(text)

            def _log_callback(message):
                runtime_logs.append(message)

            try:
                bundle = run_pdf_pipeline_for_item(current_item, _progress_callback, _log_callback)
                description_payload = bundle["description"]
                triples_payload = bundle["triples"]
                ocr_terms = bundle["ocr_terms"]
                st.session_state.pdf_last_run_logs = runtime_logs
                st.session_state.pdf_last_run_image_id = current_item["image_id"]
                st.session_state.pdf_results_visible = True
                st.session_state.pdf_loaded_result_key = current_result_key
                append_operation_history(
                    "pdf_operation_history",
                    "pdf_operation_text_logs",
                    "在线运行当前图片",
                    [f"图片：{current_item.get('image_id', '无')}"] + runtime_logs[-3:],
                )
                current_log_lines = build_pdf_log_lines(current_item, bundle)
                status_holder.success("当前图片在线执行完成")
                st.success("已完成 OCR → Description → 三元组抽取 → 语义融合（fusion.semantic_dedup_conflict.v1）。")
            except Exception as exc:
                st.session_state.pdf_last_run_logs = runtime_logs + [f"[ERROR] {exc}"]
                st.session_state.pdf_last_run_image_id = current_item["image_id"]
                append_operation_history(
                    "pdf_operation_history",
                    "pdf_operation_text_logs",
                    "在线运行当前图片",
                    [f"图片：{current_item.get('image_id', '无')}", str(exc)],
                    status="失败",
                )
                status_holder.error(f"执行失败：{exc}")
            load_pdf_manifest.clear()
    with action_col3:
        if st.button("🗂️ 导出当前图片结果", width='stretch', key="pdf_export_current"):
            export_dir = export_pdf_image_snapshot(current_item, bundle, current_log_lines)
            st.session_state.pdf_last_export_dir = str(export_dir)
            append_operation_history(
                "pdf_operation_history",
                "pdf_operation_text_logs",
                "归档当前图片结果",
                [f"图片：{current_item.get('image_id', '无')}", f"目录：{export_dir}"]
            )
            st.success(f"当前图片结果已归档到：{export_dir}")
    with action_col4:
        if st.session_state.pdf_last_export_dir:
            st.caption(f"最近 PDF 归档：`{st.session_state.pdf_last_export_dir}`")

    # ── 质量评估 + LLM 修复工作流 ──
    has_eval = hasattr(st.session_state, "pdf_eval_result") and bool(st.session_state.pdf_eval_result)
    with st.expander("📊 质量评估 & 自动修复", expanded=has_eval):
        st.caption("调用 Qwen-VL-Plus 评估当前图片的三元组质量，并可根据评估结果自动调用 LLM 修复问题。")
        eval_btn_col1, eval_btn_col2 = st.columns([1, 1.5])
        with eval_btn_col1:
            do_eval = st.button("🖼️ 在线评估三元组质量", width="stretch", key=f"pdf_online_eval_{current_item.get('image_id','')}",
                                help="Qwen-VL-Plus 对比图片+OCR+三元组，给出结构化评分和逐条修复建议（消耗 API 额度）")
        with eval_btn_col2:
            if hasattr(st.session_state, "pdf_eval_result") and st.session_state.pdf_eval_result:
                er = st.session_state.pdf_eval_result
                if "overall_score" in er:
                    st.caption(f"上次评估: 综合 {er.get('overall_score','?')}/10 | 问题 {len(er.get('issues',[]))} 条")

        if do_eval:
            with st.spinner("Qwen-VL-Plus 正在评估（约 10-30 秒）..."):
                try:
                    import eval_online
                    er = eval_online.evaluate_single(current_item["image_id"], eval_online.load_manifest())
                    st.session_state.pdf_eval_result = er
                    if "overall_score" in er:
                        st.success(f"评估完成：综合 {er['overall_score']}/10，发现 {len(er.get('issues',[]))} 个问题")
                    elif "error" in er:
                        st.warning(f"评估问题: {er['error']}")
                    else:
                        st.error("评估失败")
                except Exception as exc:
                    st.error(f"评估出错: {exc}")

        # ── 展示评估结果 + 逐条修复 ──
        if hasattr(st.session_state, "pdf_eval_result") and st.session_state.pdf_eval_result:
            er = st.session_state.pdf_eval_result
            if "overall_score" in er:
                st.markdown("---")
                st.markdown("#### 评估分数")
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("综合", f"{er.get('overall_score','?')}")
                c2.metric("OCR", f"{er.get('ocr_completeness','?')}")
                c3.metric("描述", f"{er.get('description_accuracy','?')}")
                c4.metric("精确率", f"{er.get('triple_precision','?')}")
                c5.metric("召回率", f"{er.get('triple_recall','?')}")

                issues = er.get("issues", [])
                corrections = er.get("corrections", [])
                if issues:
                    st.markdown("#### 逐条问题 & 修复")

                    image_id = er.get("image_id", "")
                    doc_name = er.get("doc_name", "")

                    # Track which corrections have been applied
                    applied_key = f"_pdf_applied_corrections_{image_id}"
                    if applied_key not in st.session_state:
                        st.session_state[applied_key] = set()

                    for i, iss in enumerate(issues):
                        is_applied = i in st.session_state[applied_key]
                        severity_colors = {"critical": "#dc2626", "major": "#d97706", "minor": "#64748b"}
                        sc = severity_colors.get(iss.get("severity", "minor"), "#64748b")
                        indices = iss.get("triple_indices", [])

                        # Find matching correction for this issue
                        corr = corrections[i] if i < len(corrections) else None
                        action = corr.get("action", "?") if corr else "?"
                        action_colors = {"delete": "#dc2626", "modify": "#d97706", "add": "#2563eb"}
                        action_badge = f"<span style='display:inline-block;background:{action_colors.get(action,'#64748b')};color:#fff;padding:1px 8px;border-radius:8px;font-size:0.7rem;font-weight:700;'>{action}</span>"

                        if is_applied:
                            st.markdown(
                                f"""<div style="border-left:4px solid #059669;padding:6px 10px;margin:6px 0;background:#f0fdf4;">
                                <b style="color:#059669;">[已应用]</b> {action_badge}
                                {iss.get('issue_type','?')} &nbsp; triples: {indices}<br/>
                                <span style="color:#334155;">{iss.get('description','')}</span>
                                </div>""", unsafe_allow_html=True)
                        else:
                            corrected_preview = ""
                            if corr:
                                ch = corr.get("corrected_head","")
                                cr = corr.get("corrected_relation","")
                                ct = corr.get("corrected_tail","")
                                reason = corr.get("reason","")
                                corrected_preview = f"<br/><span style='color:#059669;'>→ <b>{action}</b>: ({ch[:30]}, {cr[:20]}, {ct[:30]})</span>"
                                if reason:
                                    corrected_preview += f"<br/><span style='color:#64748b;font-size:0.8rem;'>{reason}</span>"
                            st.markdown(
                                f"""<div style="border-left:4px solid {sc};padding:6px 10px;margin:6px 0;background:#f8fafc;">
                                <b style="color:{sc};">[{iss.get('severity','?').upper()}] {iss.get('issue_type','?')}</b>
                                &nbsp; triples: {indices}<br/>
                                <span style="color:#334155;">{iss.get('description','')}</span>
                                {corrected_preview}
                                </div>""", unsafe_allow_html=True)

                    # ── Confirm Corrections Table ──
                    if corrections and not all(i in st.session_state[applied_key] for i in range(len(corrections))):
                        st.markdown("---")
                        st.markdown("#### 建议修改列表（审核后确认应用）")

                        corr_rows = []
                        for i, corr in enumerate(corrections):
                            if i in st.session_state[applied_key]:
                                continue
                            indices_str = ",".join(str(x) for x in corr.get("triple_indices", []))
                            corr_rows.append({
                                "#": i,
                                "操作": corr.get("action","?"),
                                "影响行": indices_str,
                                "head": corr.get("corrected_head",""),
                                "relation": corr.get("corrected_relation",""),
                                "tail": corr.get("corrected_tail",""),
                                "原因": corr.get("reason","")[:60],
                                "确认": True,
                            })

                        if corr_rows:
                            corr_df = pd.DataFrame(corr_rows)
                            edited_corr = st.data_editor(
                                corr_df, width="stretch", hide_index=True,
                                key=f"pdf_corr_editor_{image_id}", num_rows="fixed",
                                column_config={
                                    "确认": st.column_config.CheckboxColumn("确认应用", default=True),
                                    "#": st.column_config.NumberColumn("#", width="small"),
                                    "操作": st.column_config.TextColumn("操作", width="small"),
                                    "影响行": st.column_config.TextColumn("影响行", width="small"),
                                    "head": "head", "relation": "relation", "tail": "tail",
                                    "原因": st.column_config.TextColumn("原因", width="medium"),
                                },
                            )

                            if st.button("确认应用选中的修改到变更记录", width="stretch",
                                         key=f"pdf_apply_corrections_{image_id}", type="primary"):
                                changes_key = f"_pdf_changes_{image_id}"
                                changes = st.session_state.get(changes_key, {"deleted": set(), "modified": {}, "added": []})

                                for ci, row in edited_corr.iterrows():
                                    if not row.get("确认", True):
                                        continue
                                    act = str(row.get("操作",""))
                                    idx_str = str(row.get("影响行",""))
                                    idxs = [int(x) for x in idx_str.split(",") if x.strip().isdigit()]

                                    if act == "delete":
                                        for idx in idxs:
                                            changes["deleted"].add(idx)
                                    elif act == "modify":
                                        for idx in idxs:
                                            changes["modified"][idx] = {
                                                "head": str(row.get("head","")), "relation": str(row.get("relation","")),
                                                "tail": str(row.get("tail",""))
                                            }
                                    elif act == "add":
                                        changes["added"].append({
                                            "head": str(row.get("head","")), "relation": str(row.get("relation","")),
                                            "tail": str(row.get("tail",""))
                                        })

                                st.session_state[changes_key] = changes
                                for i in range(len(corrections)):
                                    st.session_state[applied_key].add(i)
                                st.success(f"已将 {len(corr_rows)} 条修改写入变更记录。请在「抽取审阅」中查看。")
                                st.rerun()


    show_pdf_results = st.session_state.pdf_results_visible and st.session_state.pdf_loaded_result_key == current_result_key
    if not show_pdf_results:
        st.info("请选择图片后，点击「查看当前图片结果」或「在线运行当前图片」，再展示处理结果。")
        return

    metric_col1, metric_col2, metric_col3 = st.columns(3)
    with metric_col1:
        render_metric_card("当前文档", current_item.get("doc_name", "-"), "当前选中的规范来源", tone="blue")
    with metric_col2:
        render_metric_card("当前图片", current_item.get("image_id", "-"), f"第 {st.session_state.pdf_image_index + 1} 张", tone="purple")
    with metric_col3:
        render_metric_card("候选三元组数", len(triples_payload), "当前图片抽取产物", tone="green")

    if description_payload.get("engineering_interpretation"):
        st.info(f"工程理解摘要：{description_payload.get('engineering_interpretation')}")

    # ── 3 个子 Tab ──
    review_tab, detail_tab, export_tab = st.tabs(["抽取审阅", "OCR & 描述", "导出归档"])

    # ── Tab 1: 抽取审阅 ──
    with review_tab:
        rleft, rright = st.columns([0.65, 1.35])
        with rleft:
            render_section_header("当前图片", "预览与基本信息。")
            resolved_img = current_item.get("resolved_image_path", current_item.get("image_path", ""))
            if resolved_img and Path(resolved_img).exists():
                st.image(resolved_img, width="stretch")
            else:
                st.warning(f"图片路径不存在。\n\n> {resolved_img}")
            st.caption(f"**文档**: {current_item.get('doc_name', '无')}")
            st.caption(f"**图片**: {current_item.get('image_id', '无')}")
            st.caption(f"**序号**: {st.session_state.pdf_image_index + 1} / {len(filtered_items)}")

        with rright:
            render_section_header("工程师校验区", "三表架构：离线缓存(溯源) → 变更记录(增删改) → 确认版本(最终)。")

            # ── 数据源 ──
            confirmed_dir = WORKBENCH_PDF_ROOT / sanitize_path_component(current_item.get("doc_name", "unknown")) / sanitize_path_component(current_item.get("image_id", "unknown"))
            confirmed_path = confirmed_dir / "confirmed.json"
            cache_source = bundle.get("fused_triples") or triples_payload

            # Initialize session state for change tracking
            img_key = current_item.get("image_id", "")
            changes_key = f"_pdf_changes_{img_key}"
            confirmed_key = f"_pdf_confirmed_{img_key}"

            if changes_key not in st.session_state:
                st.session_state[changes_key] = {"deleted": set(), "modified": {}, "added": []}

            # Build working set: cache - deleted + modified + added
            changes = st.session_state[changes_key]
            working_triples = []
            for i, t in enumerate(cache_source):
                if i in changes["modified"]:
                    working_triples.append(changes["modified"][i])
                elif i not in changes["deleted"]:
                    working_triples.append(t if isinstance(t, dict) else {"head": t[0], "relation": t[1], "tail": t[2]})
            working_triples.extend(changes["added"])

            # ── 表1: 离线缓存数据（只读）──
            cache_count = len(cache_source)
            with st.expander(f"离线缓存数据（只读溯源，共 {cache_count} 条）", expanded=False):
                cache_rows = []
                for i, t in enumerate(cache_source):
                    if isinstance(t, dict):
                        cache_rows.append({"#": i, "head": t.get("head",""), "relation": t.get("relation",""), "tail": t.get("tail","")})
                    else:
                        cache_rows.append({"#": i, "head": t[0], "relation": t[1], "tail": t[2]})
                if cache_rows:
                    st.dataframe(pd.DataFrame(cache_rows), width="stretch", hide_index=True, height=240)
                else:
                    st.caption("无离线缓存数据。")

            # ── 表2: 变更记录（可操作）──
            del_count = len(changes["deleted"])
            mod_count = len(changes["modified"])
            add_count = len(changes["added"])
            with st.expander(f"变更记录（增删改共 {del_count + mod_count + add_count} 项）", expanded=True):
                chg_tabs = st.tabs([f"删除({del_count})", f"修改({mod_count})", f"新增({add_count})"])

                with chg_tabs[0]:
                    st.caption("标记要删除的行（来自质量评估或 LLM 改写的结果）。")
                    for di in sorted(list(changes["deleted"])):
                        if di < len(cache_source):
                            t = cache_source[di]
                            t_dict = t if isinstance(t, dict) else {"head": t[0], "relation": t[1], "tail": t[2]}
                            col_a, col_b = st.columns([3, 1])
                            with col_a:
                                st.caption(f"#{di}: ({t_dict.get('head','')[:30]}, {t_dict.get('relation','')[:20]}, {t_dict.get('tail','')[:30]})")
                            with col_b:
                                if st.button("恢复", key=f"pdf_undel_{img_key}_{di}"):
                                    changes["deleted"].discard(di)
                    if not changes["deleted"]:
                        st.caption("无待删除项。")

                with chg_tabs[1]:
                    st.caption("已修改的行（来自质量评估或 LLM 改写的结果）。")
                    for mi in sorted(list(changes["modified"].keys())):
                        orig = cache_source[mi] if mi < len(cache_source) else {"head":"","relation":"","tail":""}
                        o_t = orig if isinstance(orig, dict) else {"head": orig[0], "relation": orig[1], "tail": orig[2]}
                        new_t = changes["modified"][mi]
                        st.caption(f"#{mi}: ({o_t.get('head','')[:20]}, {o_t.get('relation','')[:15]}, {o_t.get('tail','')[:20]})")
                        st.caption(f"    -> ({new_t.get('head','')[:20]}, {new_t.get('relation','')[:15]}, {new_t.get('tail','')[:20]})")
                        if st.button("撤销修改", key=f"pdf_unmod_{img_key}_{mi}"):
                            del changes["modified"][mi]
                    if not changes["modified"]:
                        st.caption("无待修改项。")

                with chg_tabs[2]:
                    st.caption("新增的三元组（来自质量评估或 LLM 改写的结果）。")
                    for ai, added in enumerate(list(changes["added"])):
                        st.caption(f"+ ({added.get('head','')[:30]}, {added.get('relation','')[:20]}, {added.get('tail','')[:30]})")
                        if st.button("移除", key=f"pdf_rmadd_{img_key}_{ai}"):
                            changes["added"].pop(ai)
                    if not changes["added"]:
                        st.caption("无新增项。")

            # ── 表3: 最终确认版本 ──
            with st.expander(f"最终确认版本（共 {len(working_triples)} 条）", expanded=True):
                working_for_editor = []
                for wi, wt in enumerate(working_triples):
                    wtd = wt if isinstance(wt, dict) else {"head": wt[0], "relation": wt[1], "tail": wt[2]}
                    working_for_editor.append({"#": wi, "head": wtd.get("head",""), "relation": wtd.get("relation",""), "tail": wtd.get("tail","")})

                if working_for_editor:
                    working_df = pd.DataFrame(working_for_editor)
                    edited_working = st.data_editor(
                        working_df[["#", "head", "relation", "tail"]],
                        width="stretch", hide_index=True, height=240, num_rows="dynamic",
                        key=f"pdf_working_editor_{img_key}",
                        column_config={
                            "#": st.column_config.NumberColumn("#", width="small"),
                            "head": st.column_config.TextColumn("head", width="medium"),
                            "relation": st.column_config.TextColumn("relation", width="small"),
                            "tail": st.column_config.TextColumn("tail", width="large"),
                        },
                    )
                else:
                    st.caption("无三元组。")
                    edited_working = pd.DataFrame()

                # ── 保存 & LLM 按钮 ──
                b1, b2, b3 = st.columns([1.2, 0.8, 1.5])
                with b1:
                    if st.button("保存确认版本", width="stretch", key=f"pdf_save_review_{img_key}", type="primary"):
                        confirmed_dir.mkdir(parents=True, exist_ok=True)
                        final_triples = []
                        if not edited_working.empty:
                            for _, r in edited_working.iterrows():
                                h, rel, t = str(r.get("head","")).strip(), str(r.get("relation","")).strip(), str(r.get("tail","")).strip()
                                if h and rel and t:
                                    final_triples.append({"head": h, "relation": rel, "tail": t})
                        payload = {
                            "image_id": img_key,
                            "doc_name": current_item.get("doc_name"),
                            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "triple_count": len(final_triples),
                            "triples": final_triples,
                        }
                        confirmed_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                        st.session_state.pdf_last_review_path = str(confirmed_path)
                        st.success(f"已保存确认版本 ({len(final_triples)} 条)")
                with b2:
                    if st.button("恢复缓存", width="stretch", key=f"pdf_reset_changes_{img_key}",
                                 help="丢弃所有变更，恢复到离线缓存原始数据。"):
                        st.session_state[changes_key] = {"deleted": set(), "modified": {}, "added": []}
                        st.rerun()
                with b3:
                    pdf_llm_clicked = st.button("LLM 改写", width="stretch", key=f"pdf_llm_reextract_{img_key}")

        # ── LLM 改写控制台 ──
        if pdf_llm_clicked:
            st.session_state["_pdf_llm_open_" + img_key] = True
        if st.session_state.get("_pdf_llm_open_" + img_key, False):
            with st.expander("LLM 改写控制台", expanded=True):
                st.caption("勾选参考三元组，OCR 上下文自动携带。改写结果添加到「新增」列表中。")
                llm_col1, llm_col2 = st.columns([1, 1.5])
                with llm_col1:
                    pdf_triples_for_sel = []
                    for wi, wt in enumerate(working_triples):
                        wtd = wt if isinstance(wt, dict) else {"head": wt[0], "relation": wt[1], "tail": wt[2]}
                        pdf_triples_for_sel.append({"head": wtd.get("head",""), "relation": wtd.get("relation",""), "tail": wtd.get("tail",""), "勾选": False})
                    pdf_sel_df = None
                    if pdf_triples_for_sel:
                        pdf_sel_df = st.data_editor(
                            pd.DataFrame(pdf_triples_for_sel), width="stretch", hide_index=True,
                            key=f"pdf_llm_select_{img_key}", num_rows="fixed",
                            column_config={"勾选": st.column_config.CheckboxColumn("参考", default=False)},
                        )
                    with st.expander("OCR 上下文", expanded=False):
                        st.code("\n".join(ocr_terms[:40]), language="text")
                    improvement = st.text_area("改进方向", placeholder="如：把 relation 改为英文...", key=f"pdf_llm_hint_{img_key}", height=60)
                with llm_col2:
                    if st.button("预览 LLM 改写", width="stretch", key=f"pdf_llm_preview_{img_key}", type="primary"):
                        with st.spinner("Qwen-Plus 改写中..."):
                            selected = []
                            if pdf_sel_df is not None:
                                for _, r in pdf_sel_df.iterrows():
                                    if r.get("勾选"):
                                        selected.append({"head": str(r.get("head","")).strip(), "relation": str(r.get("relation","")).strip(), "tail": str(r.get("tail","")).strip()})
                            ctx = {"ocr_terms": ocr_terms[:50], "table_type": description_payload.get("table_type",""),
                                   "topic": description_payload.get("topic",""),
                                   "core_entities": description_payload.get("core_entities",[])[:10],
                                   "engineering_interpretation": description_payload.get("engineering_interpretation",""),
                                   "selected_triples": selected,
                                   "existing_triples": [{k: t.get(k,"") for k in ["head","relation","tail"]} for t in (triples_payload or [])[:20]]}
                            result = llm_reextract_pdf_v2(ctx, improvement)
                            if result is None:
                                st.error("LLM 调用失败")
                            elif len(result) == 0:
                                st.warning("LLM 未返回结果")
                            else:
                                st.session_state["_pdf_llm_diff_" + img_key] = result
                                st.success(f"LLM 返回 {len(result)} 条，请在下方 diff 表中确认。")
                    diff_key = "_pdf_llm_diff_" + img_key
                    if diff_key in st.session_state and st.session_state[diff_key]:
                        st.markdown("#### 改写结果")
                        diff_rows = []
                        for t in st.session_state[diff_key]:
                            diff_rows.append({"head": t.get("head",""), "relation": t.get("relation",""), "tail": t.get("tail",""), "采纳": True})
                        diff_df = st.data_editor(
                            pd.DataFrame(diff_rows), width="stretch", hide_index=True,
                            key=f"pdf_llm_diff_editor_{img_key}", num_rows="fixed",
                            column_config={"采纳": st.column_config.CheckboxColumn("采纳", default=True)},
                        )
                        if st.button("应用采纳的改写", key=f"pdf_llm_apply_{img_key}", type="primary"):
                            chgs = st.session_state.get(changes_key, {"deleted": set(), "modified": {}, "added": []})
                            for _, row in diff_df.iterrows():
                                if row.get("采纳"):
                                    chgs["added"].append({"head": row.get("head",""), "relation": row.get("relation",""), "tail": row.get("tail","")})
                            st.session_state[changes_key] = chgs
                            del st.session_state[diff_key]
                            st.session_state["_pdf_llm_open_" + img_key] = False
                            st.success("改写已添加到「新增」列表。")
                            st.rerun()

    with detail_tab:
        d1, d2 = st.columns(2)
        with d1:
            render_section_header("OCR 术语白名单", f"共 {len(ocr_terms)} 个术语")
            with st.container(height=320):
                if ocr_terms:
                    st.code("\n".join(ocr_terms), language="text")
                else:
                    st.warning("暂无 OCR 术语结果。")
            with st.expander("OCR 明细"):
                ocr_confidence_df = build_ocr_whitelist_confidence_df(bundle["ocr_terms_payload"], bundle["ocr_full"])
                if not ocr_confidence_df.empty:
                    st.dataframe(ocr_confidence_df, width='stretch', hide_index=True)
                if bundle["ocr_text"]:
                    st.code(bundle["ocr_text"], language="text")
        with d2:
            render_section_header("Description 结构理解", f"表格类型: {description_payload.get('table_type', 'unknown')}")
            with st.container(height=320):
                render_pdf_description(description_payload, bundle["description_raw"])

        # Fusion section
        fused_triples = bundle.get("fused_triples", [])
        if fused_triples:
            with st.expander("\U0001f9e0 语义融合结果 (fusion.semantic_dedup_conflict.v1)", expanded=False):
                conflict_count = sum(1 for t in fused_triples if t.get("conflict"))
                f1, f2 = st.columns(2)
                f1.metric("融合后三元组", len(fused_triples))
                f2.metric("冲突标记", conflict_count)
                st.dataframe(pd.DataFrame(fused_triples)[["head","relation","tail","conflict"]], width='stretch', hide_index=True)

    # ── Tab 3: 导出归档 ──
    with export_tab:
        e1, e2 = st.columns(2)
        with e1:
            if st.button("归档当前图片三元组", width='stretch', key=f"pdf_export_{current_item.get('image_id', 'unknown')}"):
                export_dir = export_pdf_image_snapshot(current_item, bundle, current_log_lines)
                st.session_state.pdf_last_export_dir = str(export_dir)
                st.success(f"已归档: {export_dir}")
            if st.session_state.pdf_last_export_dir:
                st.caption(f"最近归档: `{st.session_state.pdf_last_export_dir}`")
        with e2:
            st.caption("审核历史：")
            reviewed_dir = WORKBENCH_PDF_ROOT / sanitize_path_component(current_item.get("doc_name", "unknown")) / sanitize_path_component(current_item.get("image_id", "unknown")) / "reviewed"
            if reviewed_dir.exists():
                for rf in sorted(reviewed_dir.glob("*.json"), reverse=True)[:5]:
                    st.caption(rf.name)
            else:
                st.caption("暂无审核记录。")

    # ── 阶段状态栏 ──
    with st.expander("处理记录 & 阶段状态", expanded=False):
        fused_triples = bundle.get("fused_triples", [])
        fusion_status = "已完成" if fused_triples else "未运行"
        stage_records = [
            {"阶段": "OCR", "状态": format_stage_status(bundle["paths"]["ocr_terms"].exists(), "terms.json"), "详情": f"{len(ocr_terms)} 个术语"},
            {"阶段": "Description", "状态": format_stage_status(bundle["paths"]["desc_result"].exists(), "result.json"), "详情": description_payload.get("topic", "无") if description_payload else "无"},
            {"阶段": "Triples (pdf.online_table_pipeline.v1)", "状态": format_stage_status(bundle["paths"]["triples_result"].exists(), "result.json"), "详情": f"{len(triples_payload)} 条"},
            {"阶段": "Fusion (fusion.semantic_dedup_conflict.v1)", "状态": fusion_status, "详情": f"{len(fused_triples)} 条融合后" if fused_triples else "缓存读取"},
        ]
        lc1, lc2 = st.columns([1, 1.2])
        with lc1:
            render_operation_history("pdf_operation_history", "暂无操作记录。")
        with lc2:
            st.dataframe(pd.DataFrame(stage_records), width='stretch', hide_index=True)
            combined_pdf_logs = st.session_state.pdf_operation_text_logs[-8:] + current_log_lines
            st.code("\n".join(combined_pdf_logs), language="text")


def render_incremental_workbench():
    render_hero_banner(
        "增量更新工作台",
        "围绕 pending 增、删、改进行审阅与归档。界面按案例聚焦，并通过图形化差异帮助快速理解变更。",
        "📙",
        align="left",
        compact=True,
    )
    st.caption("基于 JSONL 基线与 pending 文件进行审阅，不依赖 Neo4j。展示时内部按 `case_key + fact_hash` 理解事实作用域，避免跨案例误判。")

    if not INCREMENTAL_SCRIPT_PATH.parent.exists():
        st.error(f"未找到增量更新目录：{INCREMENTAL_SCRIPT_PATH.parent}")
        return

    runtime_modules = None
    try:
        runtime_modules = load_incremental_runtime_modules(get_incremental_runtime_cache_key())
    except Exception as exc:
        st.error(f"加载增量更新脚本失败：{exc}")
        return

    existing_domain_dirs = get_incremental_domain_dirs()
    existing_domain_names = [infer_incremental_domain_name(path) for path in existing_domain_dirs]
    preferred_domain = st.session_state.domain_name if st.session_state.domain_name else (existing_domain_names[0] if existing_domain_names else "离车上锁功能测试")

    control_col1, control_col2 = st.columns([1.2, 1])
    with control_col1:
        render_section_header("领域选择", "切换待审阅业务域，并查看对应的增量目录。")
        selected_domain_name = st.selectbox(
            "选择业务领域",
            options=existing_domain_names if existing_domain_names else [preferred_domain],
            index=(existing_domain_names.index(preferred_domain) if preferred_domain in existing_domain_names else 0),
            key="incremental_domain_select",
        )
    domain_dir = resolve_incremental_domain_dir(selected_domain_name)
    with control_col2:
        st.caption(f"当前领域目录：`{domain_dir}`")
    if st.session_state.incremental_loaded_domain != str(domain_dir):
        st.session_state.incremental_results_visible = False
        st.session_state.incremental_display_bundle = None
        st.session_state.incremental_result_source = ""

    baseline_uploader, candidate_uploader = st.columns(2)
    baseline_file = baseline_uploader.file_uploader("上传基线 Excel（可选，用于初始化 current）", type=["xlsx"], key="incremental_baseline_uploader")
    candidate_file = candidate_uploader.file_uploader("上传候选 Excel（用于生成 pending）", type=["xlsx"], key="incremental_candidate_uploader")

    action_col1, action_col2, action_col3, action_col4, action_col5 = st.columns([1, 1, 1, 1, 1.25])
    action_logs = []

    def _capture_logs(callable_obj, *args, **kwargs):
        buffer = StringIO()
        with contextlib.redirect_stdout(buffer):
            callable_obj(*args, **kwargs)
        return [line for line in buffer.getvalue().splitlines() if line.strip()]

    with action_col1:
        if st.button("初始化基线", width='stretch', key="incremental_init_current"):
            if baseline_file is None:
                st.warning("请先上传基线 Excel。")
            else:
                baseline_path = save_uploaded_file(baseline_file, WORKBENCH_INCREMENTAL_ROOT / sanitize_path_component(selected_domain_name) / "uploads")
                try:
                    init_logs = _capture_logs(
                        runtime_modules["initialize_current_baseline"],
                        str(baseline_path),
                        selected_domain_name,
                        str(domain_dir),
                        True,
                    )
                    action_logs.extend(init_logs or [f"[INIT] 已初始化基线：{baseline_path}"])
                    set_incremental_display_bundle(domain_dir, "本次初始化后的最新结果")
                    append_operation_history("incremental_operation_history", "incremental_last_logs", "初始化基线", [f"文件：{baseline_path}"] + action_logs[-3:])
                    st.success("基线初始化完成。")
                except Exception as exc:
                    append_operation_history("incremental_operation_history", "incremental_last_logs", "初始化基线", [str(exc)], status="失败")
                    st.error(f"初始化基线失败：{exc}")

    with action_col2:
        if st.button("生成增量 pending", width='stretch', key="incremental_generate_pending"):
            if candidate_file is None:
                st.warning("请先上传候选 Excel。")
            else:
                candidate_path = save_uploaded_file(candidate_file, WORKBENCH_INCREMENTAL_ROOT / sanitize_path_component(selected_domain_name) / "uploads")
                try:
                    diff_logs = _capture_logs(
                        runtime_modules["process_candidate_excel"],
                        str(candidate_path),
                        selected_domain_name,
                        str(domain_dir),
                    )
                    action_logs.extend(diff_logs or [f"[PENDING] 已生成增量：{candidate_path}"])
                    set_incremental_display_bundle(domain_dir, "本次生成 pending 的最新结果")
                    append_operation_history("incremental_operation_history", "incremental_last_logs", "生成增量 pending", [f"文件：{candidate_path}"] + action_logs[-3:])
                    st.success("已生成 pending 增量结果。")
                except Exception as exc:
                    append_operation_history("incremental_operation_history", "incremental_last_logs", "生成增量 pending", [str(exc)], status="失败")
                    st.error(f"生成 pending 失败：{exc}")

    with action_col3:
        if st.button("应用 pending 到 current", width='stretch', key="incremental_apply_pending"):
            try:
                apply_logs = _capture_logs(runtime_modules["apply_domain_pending"], str(domain_dir))
                action_logs.extend(apply_logs or [f"[APPLY] 已应用 pending：{domain_dir}"])
                set_incremental_display_bundle(domain_dir, "本次应用 pending 后的最新结果")
                append_operation_history("incremental_operation_history", "incremental_last_logs", "应用 pending 到 current", [f"领域：{domain_dir}"] + action_logs[-3:])
                st.success("已将 pending 应用到 current。")
            except Exception as exc:
                append_operation_history("incremental_operation_history", "incremental_last_logs", "应用 pending 到 current", [str(exc)], status="失败")
                st.error(f"应用 pending 失败：{exc}")

    with action_col4:
        if st.button("加载当前领域结果", width='stretch', key="incremental_show_results"):
            set_incremental_display_bundle(domain_dir, "当前领域目录中的已保存结果")

    bundle = st.session_state.incremental_display_bundle
    if bundle is not None and Path(bundle.get("domain_dir", "")) != domain_dir:
        bundle = None
    case_summaries = build_incremental_case_summaries(bundle) if bundle is not None else []

    with action_col5:
        if st.button("🗂️ 归档当前增量结果", width='stretch', key="incremental_export_snapshot"):
            if bundle is None:
                st.warning("当前还没有可归档的展示结果。请先执行初始化 / 生成 / 应用，或点击「加载当前领域结果」。")
            else:
                export_dir = export_incremental_snapshot(bundle, case_summaries)
                st.session_state.incremental_last_export_dir = str(export_dir)
                append_operation_history("incremental_operation_history", "incremental_last_logs", "归档当前增量结果", [f"归档目录：{export_dir}"])
                st.success(f"已归档到：{export_dir}")

    if st.session_state.incremental_last_export_dir:
        st.caption(f"最近增量归档：`{st.session_state.incremental_last_export_dir}`")

    if not st.session_state.incremental_results_visible or st.session_state.incremental_loaded_domain != str(domain_dir) or bundle is None:
        st.info("默认不会自动读取领域目录里的旧结果。请先执行初始化/生成/应用操作查看本次最新结果；只有点击「加载当前领域结果」时才会读取已保存文件。")
        render_section_header("处理日志", "记录最近在增量工作台完成的操作。")
        render_operation_history("incremental_operation_history", "暂时还没有操作记录。")
        return

    st.caption(f"当前展示来源：`{st.session_state.incremental_result_source or '未标记来源'}`")

    pending_add_records = deduplicate_incremental_records(bundle["pending_add"])
    pending_remove_records = deduplicate_incremental_records(bundle["pending_remove"])
    pending_changed_records = deduplicate_incremental_records(bundle["pending_changed"])
    metric_col1, metric_col2, metric_col3, metric_col4, metric_col5 = st.columns(5)
    add_triple_count = sum(1 for record in bundle["pending_add"] if record.get("record_type") == "triple")
    new_case_count = sum(1 for record in bundle["pending_add"] if record.get("record_type") == "case_marker")
    with metric_col1:
        render_metric_card("待新增案例", new_case_count, "整案新增", tone="green")
    with metric_col2:
        render_metric_card("待增加三元组", add_triple_count, "pending_add 中 triple 记录", tone="blue")
    with metric_col3:
        render_metric_card("待删除三元组", len(bundle["pending_remove"]), "extract.py 写入的 pending_remove 原始总量", tone="red")
    with metric_col4:
        render_metric_card("待更新逻辑对", len(bundle["pending_changed"]), "按修正后的严格配对规则生成的 pending_changed 原始总量", tone="amber")
    with metric_col5:
        render_metric_card("涉及案例数", len(case_summaries), "当前领域内受影响案例", tone="purple")
    st.caption(
        f"审阅说明：顶部指标保持与 `增量更新/extract.py` 写入文件一致（原始 pending 条数）；"
        f"同名案例会先按事实重叠度匹配到最像的 current 案例；逻辑变更只统计同案例、同关系且旧/新三元组共享 head 或 tail 的严格配对；"
        f"当前案例明细与图谱使用去重后的案例内记录，避免重复行把图谱挤坏。"
    )

    relation_df = build_incremental_relation_summary(bundle)
    if not relation_df.empty:
        render_section_header("关系维度分布", "从关系类型视角观察增删改热点；待更新仅统计严格 old/new 配对成功的关系。")
        st.dataframe(relation_df, width='stretch', hide_index=True)

    if not case_summaries:
        st.info("当前领域还没有 pending 结果。你可以先上传基线 Excel 初始化，再上传候选 Excel 生成待审阅增量。")
        if st.session_state.incremental_last_logs:
            st.code("\n".join(st.session_state.incremental_last_logs), language="text")
        return

    summary_df = pd.DataFrame(case_summaries)
    filter_col1, filter_col2, filter_col3 = st.columns([2, 1.3, 1.3])
    case_search = filter_col1.text_input("搜索案例名称 / ID", value="", key="incremental_case_search")
    change_kind = filter_col2.selectbox("筛选变更类型", options=["全部", "new_case_add", "changed_case_add", "changed_case_remove", "logic_change"], key="incremental_change_filter")
    sort_mode = filter_col3.selectbox("排序方式", options=["案例顺序", "待更新优先", "待删除优先", "待增加优先"], key="incremental_sort_mode")

    filtered_df = summary_df.copy()
    if case_search:
        mask = filtered_df["case_name"].str.contains(case_search, case=False, na=False) | filtered_df["case_id"].str.contains(case_search, case=False, na=False)
        filtered_df = filtered_df[mask]
    if change_kind != "全部":
        filtered_df = filtered_df[filtered_df["change_types"].str.contains(change_kind, na=False)]

    if sort_mode == "待更新优先":
        filtered_df = filtered_df.sort_values(["changed_count", "remove_count", "add_count", "row"], ascending=[False, False, False, True])
    elif sort_mode == "待删除优先":
        filtered_df = filtered_df.sort_values(["remove_count", "changed_count", "add_count", "row"], ascending=[False, False, False, True])
    elif sort_mode == "待增加优先":
        filtered_df = filtered_df.sort_values(["add_count", "changed_count", "remove_count", "row"], ascending=[False, False, False, True])
    else:
        filtered_df = filtered_df.sort_values(["row", "case_name"])

    render_section_header("案例级增量总览", "先从案例维度观察，再下钻查看单案例细节。")
    st.dataframe(
        filtered_df[["row", "case_id", "case_name", "new_case", "add_count", "remove_count", "changed_count", "change_types", "net_delta"]],
        width='stretch',
        hide_index=True,
    )

    selectable_case_rows = filtered_df.to_dict("records")
    selectable_case_keys = [row["case_key"] for row in selectable_case_rows]
    case_lookup = {row["case_key"]: row for row in selectable_case_rows}
    if not selectable_case_keys:
        st.warning("筛选后没有案例可展示。")
        return

    preferred_case = max(
        selectable_case_rows,
        key=lambda row: (row["changed_count"], row["remove_count"], row["add_count"], -row["row"]),
    )
    default_key = preferred_case["case_key"]
    default_idx = selectable_case_keys.index(default_key) if default_key in selectable_case_keys else 0
    selectbox_kwargs = {
        "label": "选择案例查看详细变更",
        "options": selectable_case_keys,
        "format_func": lambda key: f"{case_lookup[key]['case_name']} | +{case_lookup[key]['add_count']} -{case_lookup[key]['remove_count']} ~{case_lookup[key]['changed_count']}",
        "key": "incremental_case_select",
    }
    if st.session_state.get("incremental_case_select") not in selectable_case_keys:
        st.session_state.pop("incremental_case_select", None)
        selectbox_kwargs["index"] = default_idx
    selected_case_key = st.selectbox(**selectbox_kwargs)
    st.session_state.incremental_selected_case_key = selected_case_key
    selected_case_summary = case_lookup[selected_case_key]
    selected_case_detail = get_incremental_case_detail(bundle, selected_case_key)

    overview_col1, overview_col2 = st.columns([1.05, 1.95])
    with overview_col1:
        render_section_header("当前案例摘要", "聚合查看该案例的主键、类型与变更规模；待更新只统计严格匹配成功的逻辑对。")
        render_chip_group("当前案例", [selected_case_summary["case_name"], selected_case_summary["change_types"]], tone="amber")
        render_toggle_kv_panel(
            "显示案例详细信息",
            [
                ("案例名称", selected_case_summary["case_name"]),
                ("案例类型", selected_case_summary["case_id"]),
                ("案例锚点", selected_case_summary["case_anchor"]),
                ("case_key", selected_case_summary["case_key"]),
                ("变更类型", selected_case_summary["change_types"]),
                ("待增加", f"{selected_case_summary['add_count']} 条"),
                ("待删除", f"{selected_case_summary['remove_count']} 条"),
                ("待更新", f"{selected_case_summary['changed_count']} 对"),
            ],
            tone="amber",
            key=f"incremental_case_detail_{selected_case_summary['case_key']}",
            default=False,
        )
        if selected_case_detail["case_marker"]:
            st.info("该案例是新案例，将作为整案新增。")
        else:
            st.caption("当前案例若存在同名重复项，后端会先在同一案例锚点组内按事实重叠度匹配最像的一项，再计算增量。")

    with overview_col2:
        render_section_header("增量关系图", "按待增加、待删除、逻辑变更三类分开展示；逻辑变更仅展示严格 old/new 配对成功的记录。")
        st.caption(
            f"上方统计是当前领域原始 pending 总量；下方图谱只展示当前选中案例 `{selected_case_summary['case_name']}` 的去重后变更。"
            f"逻辑变更图谱中的每一对 old/new 记录，都满足同案例、同关系且共享 head 或 tail。"
        )
        graph_config = Config(
            width=860,
            height=420,
            directed=True,
            physics=True,
            hierarchical=False,
            nodeHighlightBehavior=True,
            highlightColor="#F6E05E",
        )
        graph_tab_add, graph_tab_remove, graph_tab_changed = st.tabs(["待增加图谱", "待删除图谱", "逻辑变更图谱"])
        with graph_tab_add:
            add_nodes, add_edges = build_incremental_category_graph(selected_case_summary, selected_case_detail, "add")
            if add_nodes:
                agraph(nodes=add_nodes, edges=add_edges, config=graph_config)
            else:
                st.caption("当前案例没有待增加图谱。")
        with graph_tab_remove:
            remove_nodes, remove_edges = build_incremental_category_graph(selected_case_summary, selected_case_detail, "remove")
            if remove_nodes:
                agraph(nodes=remove_nodes, edges=remove_edges, config=graph_config)
            else:
                st.caption("当前案例没有待删除图谱。")
        with graph_tab_changed:
            changed_nodes, changed_edges = build_incremental_category_graph(selected_case_summary, selected_case_detail, "changed")
            if changed_nodes:
                agraph(nodes=changed_nodes, edges=changed_edges, config=graph_config)
            else:
                st.caption("当前案例没有逻辑变更图谱。")

    render_section_header("三类增量明细", "按案例查看新增、删除与逻辑变更的详细记录；待更新明细只显示严格配对成功的 old/new 逻辑对。")
    tab_add, tab_remove, tab_changed = st.tabs(["待增加", "待删除", "逻辑更新对"])

    with tab_add:
        add_df = flatten_incremental_records(selected_case_detail["add_records"])
        if not add_df.empty:
            st.dataframe(add_df[["row", "case_name", "head", "relation", "tail", "fact_hash"]], width='stretch', hide_index=True)
        else:
            st.caption("当前案例无待增加三元组。")
        with st.expander("查看待增加 JSON"):
            st.json(selected_case_detail["add_records"])

    with tab_remove:
        remove_df = flatten_incremental_records(selected_case_detail["remove_records"])
        if not remove_df.empty:
            st.dataframe(remove_df[["row", "case_name", "head", "relation", "tail", "fact_hash"]], width='stretch', hide_index=True)
        else:
            st.caption("当前案例无待删除三元组。")
        with st.expander("查看待删除 JSON"):
            st.json(selected_case_detail["remove_records"])

    with tab_changed:
        changed_df = flatten_changed_records(selected_case_detail["changed_records"])
        if not changed_df.empty:
            st.caption("这里的待更新来自 `extract.py` 的严格配对结果，不等于把所有待删除与待增加记录简单两两组合。")
            st.dataframe(changed_df[["row", "case_name", "relation", "old_head", "old_tail", "new_head", "new_tail"]], width='stretch', hide_index=True)
            for row in changed_df.itertuples(index=False):
                compare_col1, compare_col2 = st.columns(2)
                with compare_col1:
                    render_diff_triplet_card("旧逻辑", f"({row.old_head}, {row.relation}, {row.old_tail})", tone="red")
                with compare_col2:
                    render_diff_triplet_card("新逻辑", f"({row.new_head}, {row.relation}, {row.new_tail})", tone="green")
        else:
            st.caption("当前案例无待更新逻辑对。")
        with st.expander("查看逻辑更新对 JSON"):
            st.json(selected_case_detail["changed_records"])

    render_section_header("处理日志", "记录几点完成了什么操作，并保留关键输出信息。")
    log_col1, log_col2 = st.columns([1.05, 1.35])
    with log_col1:
        render_operation_history("incremental_operation_history", "暂时还没有操作记录。")
    with log_col2:
        combined_logs = st.session_state.incremental_last_logs or [
            f"[{current_log_timestamp()}] 当前领域：{bundle['domain_name']}",
            f"  - 目录：{bundle['domain_dir']}",
            f"  - 汇总：add={add_triple_count}, remove={len(bundle['pending_remove'])}, changed={len(bundle['pending_changed'])}",
        ]
        st.code("\n".join(combined_logs), language="text")




# ═══════════════════════════════════════════════════════════════════
# 增量更新工作台 (from legacy_app.py)
# ═══════════════════════════════════════════════════════════════════

def render_incremental_workbench():
    render_hero_banner(
        "增量更新工作台",
        "围绕 pending 增、删、改进行审阅与归档。界面按案例聚焦，并通过图形化差异帮助快速理解变更。",
        "📙",
        align="left",
        compact=True,
    )
    st.caption("基于 JSONL 基线与 pending 文件进行审阅，不依赖 Neo4j。展示时内部按 case_key + fact_hash 理解事实作用域，避免跨案例误判。")

    if not INCREMENTAL_SCRIPT_PATH.parent.exists():
        st.error(f"未找到增量更新目录：{INCREMENTAL_SCRIPT_PATH.parent}")
        return

    runtime_modules = None
    try:
        runtime_modules = load_incremental_runtime_modules(get_incremental_runtime_cache_key())
    except Exception as exc:
        st.error(f"加载增量更新脚本失败：{exc}")
        return

    existing_domain_dirs = get_incremental_domain_dirs()
    existing_domain_names = [infer_incremental_domain_name(path) for path in existing_domain_dirs]
    preferred_domain = st.session_state.domain_name if st.session_state.domain_name else (existing_domain_names[0] if existing_domain_names else "离车上锁功能测试")

    control_col1, control_col2 = st.columns([1.2, 1])
    with control_col1:
        render_section_header("领域选择", "切换待审阅业务域，并查看对应的增量目录。")
        selected_domain_name = st.selectbox(
            "选择业务领域",
            options=existing_domain_names if existing_domain_names else [preferred_domain],
            index=(existing_domain_names.index(preferred_domain) if preferred_domain in existing_domain_names else 0),
            key="incremental_domain_select",
        )
    domain_dir = resolve_incremental_domain_dir(selected_domain_name)
    with control_col2:
        st.caption(f"当前领域目录：`{domain_dir}`")
    if st.session_state.incremental_loaded_domain != str(domain_dir):
        st.session_state.incremental_results_visible = False
        st.session_state.incremental_display_bundle = None
        st.session_state.incremental_result_source = ""

    baseline_uploader, candidate_uploader = st.columns(2)
    baseline_file = baseline_uploader.file_uploader("上传基线 Excel（可选，用于初始化 current）", type=["xlsx"], key="incremental_baseline_uploader")
    candidate_file = candidate_uploader.file_uploader("上传候选 Excel（用于生成 pending）", type=["xlsx"], key="incremental_candidate_uploader")

    action_col1, action_col2, action_col3, action_col4, action_col5 = st.columns([1, 1, 1, 1, 1.25])
    action_logs = []

    def _capture_logs(callable_obj, *args, **kwargs):
        buffer = StringIO()
        with contextlib.redirect_stdout(buffer):
            callable_obj(*args, **kwargs)
        return [line for line in buffer.getvalue().splitlines() if line.strip()]

    with action_col1:
        if st.button("初始化基线", width='stretch', key="incremental_init_current"):
            if baseline_file is None:
                st.warning("请先上传基线 Excel。")
            else:
                baseline_path = save_uploaded_file(baseline_file, WORKBENCH_INCREMENTAL_ROOT / sanitize_path_component(selected_domain_name) / "uploads")
                try:
                    init_logs = _capture_logs(
                        runtime_modules["initialize_current_baseline"],
                        str(baseline_path),
                        selected_domain_name,
                        str(domain_dir),
                        True,
                    )
                    action_logs.extend(init_logs or [f"[INIT] 已初始化基线：{baseline_path}"])
                    set_incremental_display_bundle(domain_dir, "本次初始化后的最新结果")
                    append_operation_history("incremental_operation_history", "incremental_last_logs", "初始化基线", [f"文件：{baseline_path}"] + action_logs[-3:])
                    st.success("基线初始化完成。")
                except Exception as exc:
                    append_operation_history("incremental_operation_history", "incremental_last_logs", "初始化基线", [str(exc)], status="失败")
                    st.error(f"初始化基线失败：{exc}")

    with action_col2:
        if st.button("生成增量 pending", width='stretch', key="incremental_generate_pending"):
            if candidate_file is None:
                st.warning("请先上传候选 Excel。")
            else:
                candidate_path = save_uploaded_file(candidate_file, WORKBENCH_INCREMENTAL_ROOT / sanitize_path_component(selected_domain_name) / "uploads")
                try:
                    diff_logs = _capture_logs(
                        runtime_modules["process_candidate_excel"],
                        str(candidate_path),
                        selected_domain_name,
                        str(domain_dir),
                    )
                    action_logs.extend(diff_logs or [f"[PENDING] 已生成增量：{candidate_path}"])
                    set_incremental_display_bundle(domain_dir, "本次生成 pending 的最新结果")
                    append_operation_history("incremental_operation_history", "incremental_last_logs", "生成增量 pending", [f"文件：{candidate_path}"] + action_logs[-3:])
                    st.success("已生成 pending 增量结果。")
                except Exception as exc:
                    append_operation_history("incremental_operation_history", "incremental_last_logs", "生成增量 pending", [str(exc)], status="失败")
                    st.error(f"生成 pending 失败：{exc}")

    with action_col3:
        if st.button("应用 pending 到 current", width='stretch', key="incremental_apply_pending"):
            try:
                apply_logs = _capture_logs(runtime_modules["apply_domain_pending"], str(domain_dir))
                action_logs.extend(apply_logs or [f"[APPLY] 已应用 pending：{domain_dir}"])
                set_incremental_display_bundle(domain_dir, "本次应用 pending 后的最新结果")
                append_operation_history("incremental_operation_history", "incremental_last_logs", "应用 pending 到 current", [f"领域：{domain_dir}"] + action_logs[-3:])
                st.success("已将 pending 应用到 current。")
            except Exception as exc:
                append_operation_history("incremental_operation_history", "incremental_last_logs", "应用 pending 到 current", [str(exc)], status="失败")
                st.error(f"应用 pending 失败：{exc}")

    with action_col4:
        if st.button("加载当前领域结果", width='stretch', key="incremental_show_results"):
            set_incremental_display_bundle(domain_dir, "当前领域目录中的已保存结果")

    bundle = st.session_state.incremental_display_bundle
    if bundle is not None and Path(bundle.get("domain_dir", "")) != domain_dir:
        bundle = None
    case_summaries = build_incremental_case_summaries(bundle) if bundle is not None else []

    with action_col5:
        if st.button("🗂️ 归档当前增量结果", width='stretch', key="incremental_export_snapshot"):
            if bundle is None:
                st.warning("当前还没有可归档的展示结果。请先执行初始化 / 生成 / 应用，或点击「加载当前领域结果」。")
            else:
                export_dir = export_incremental_snapshot(bundle, case_summaries)
                st.session_state.incremental_last_export_dir = str(export_dir)
                append_operation_history("incremental_operation_history", "incremental_last_logs", "归档当前增量结果", [f"归档目录：{export_dir}"])
                st.success(f"已归档到：{export_dir}")

    if st.session_state.incremental_last_export_dir:
        st.caption(f"最近增量归档：`{st.session_state.incremental_last_export_dir}`")

    if not st.session_state.incremental_results_visible or st.session_state.incremental_loaded_domain != str(domain_dir) or bundle is None:
        st.info("默认不会自动读取领域目录里的旧结果。请先执行初始化/生成/应用操作查看本次最新结果；只有点击「加载当前领域结果」时才会读取已保存文件。")
        render_section_header("处理日志", "记录最近在增量工作台完成的操作。")
        render_operation_history("incremental_operation_history", "暂时还没有操作记录。")
        return

    st.caption(f"当前展示来源：`{st.session_state.incremental_result_source or '未标记来源'}`")

    pending_add_records = deduplicate_incremental_records(bundle["pending_add"])
    pending_remove_records = deduplicate_incremental_records(bundle["pending_remove"])
    pending_changed_records = deduplicate_incremental_records(bundle["pending_changed"])
    metric_col1, metric_col2, metric_col3, metric_col4, metric_col5 = st.columns(5)
    add_triple_count = sum(1 for record in bundle["pending_add"] if record.get("record_type") == "triple")
    new_case_count = sum(1 for record in bundle["pending_add"] if record.get("record_type") == "case_marker")
    with metric_col1:
        render_metric_card("待新增案例", new_case_count, "整案新增", tone="green")
    with metric_col2:
        render_metric_card("待增加三元组", add_triple_count, "pending_add 中 triple 记录", tone="blue")
    with metric_col3:
        render_metric_card("待删除三元组", len(bundle["pending_remove"]), "pending_remove 原始总量", tone="red")
    with metric_col4:
        render_metric_card("待更新逻辑对", len(bundle["pending_changed"]), "严格配对生成的 changed 记录", tone="amber")
    with metric_col5:
        render_metric_card("涉及案例数", len(case_summaries), "当前领域内受影响案例", tone="purple")
    st.caption(
        f"审阅说明：同名案例会先按事实重叠度匹配到最像的 current 案例；"
        f"逻辑变更只统计同案例、同关系且旧/新三元组共享 head 或 tail 的严格配对。"
    )

    relation_df = build_incremental_relation_summary(bundle)
    if not relation_df.empty:
        render_section_header("关系维度分布", "从关系类型视角观察增删改热点。")
        st.dataframe(relation_df, width='stretch', hide_index=True)

    if not case_summaries:
        st.info("当前领域还没有 pending 结果。你可以先上传基线 Excel 初始化，再上传候选 Excel 生成待审阅增量。")
        if st.session_state.incremental_last_logs:
            st.code("\n".join(st.session_state.incremental_last_logs), language="text")
        return

    summary_df = pd.DataFrame(case_summaries)
    filter_col1, filter_col2, filter_col3 = st.columns([2, 1.3, 1.3])
    case_search = filter_col1.text_input("搜索案例名称 / ID", value="", key="incremental_case_search")
    change_kind = filter_col2.selectbox("筛选变更类型", options=["全部", "new_case_add", "changed_case_add", "changed_case_remove", "logic_change"], key="incremental_change_filter")
    sort_mode = filter_col3.selectbox("排序方式", options=["案例顺序", "待更新优先", "待删除优先", "待增加优先"], key="incremental_sort_mode")

    filtered_df = summary_df.copy()
    if case_search:
        mask = filtered_df["case_name"].str.contains(case_search, case=False, na=False) | filtered_df["case_id"].str.contains(case_search, case=False, na=False)
        filtered_df = filtered_df[mask]
    if change_kind != "全部":
        filtered_df = filtered_df[filtered_df["change_types"].str.contains(change_kind, na=False)]

    if sort_mode == "待更新优先":
        filtered_df = filtered_df.sort_values(["changed_count", "remove_count", "add_count", "row"], ascending=[False, False, False, True])
    elif sort_mode == "待删除优先":
        filtered_df = filtered_df.sort_values(["remove_count", "changed_count", "add_count", "row"], ascending=[False, False, False, True])
    elif sort_mode == "待增加优先":
        filtered_df = filtered_df.sort_values(["add_count", "changed_count", "remove_count", "row"], ascending=[False, False, False, True])
    else:
        filtered_df = filtered_df.sort_values(["row", "case_name"])

    render_section_header("案例级增量总览", "先从案例维度观察，再下钻查看单案例细节。")
    st.dataframe(
        filtered_df[["row", "case_id", "case_name", "new_case", "add_count", "remove_count", "changed_count", "change_types", "net_delta"]],
        width='stretch',
        hide_index=True,
    )

    selectable_case_rows = filtered_df.to_dict("records")
    selectable_case_keys = [row["case_key"] for row in selectable_case_rows]
    case_lookup = {row["case_key"]: row for row in selectable_case_rows}
    if not selectable_case_keys:
        st.warning("筛选后没有案例可展示。")
        return

    preferred_case = max(
        selectable_case_rows,
        key=lambda row: (row["changed_count"], row["remove_count"], row["add_count"], -row["row"]),
    )
    default_key = preferred_case["case_key"]
    default_idx = selectable_case_keys.index(default_key) if default_key in selectable_case_keys else 0
    selectbox_kwargs = {
        "label": "选择案例查看详细变更",
        "options": selectable_case_keys,
        "format_func": lambda key: f"{case_lookup[key]['case_name']} | +{case_lookup[key]['add_count']} -{case_lookup[key]['remove_count']} ~{case_lookup[key]['changed_count']}",
        "key": "incremental_case_select",
    }
    if st.session_state.get("incremental_case_select") not in selectable_case_keys:
        st.session_state.pop("incremental_case_select", None)
        selectbox_kwargs["index"] = default_idx
    selected_case_key = st.selectbox(**selectbox_kwargs)
    st.session_state.incremental_selected_case_key = selected_case_key
    selected_case_summary = case_lookup[selected_case_key]
    selected_case_detail = get_incremental_case_detail(bundle, selected_case_key)

    overview_col1, overview_col2 = st.columns([1.05, 1.95])
    with overview_col1:
        render_section_header("当前案例摘要", "聚合查看该案例的主键、类型与变更规模。")
        render_chip_group("当前案例", [selected_case_summary["case_name"], selected_case_summary["change_types"]], tone="amber")
        render_toggle_kv_panel(
            "显示案例详细信息",
            [
                ("案例名称", selected_case_summary["case_name"]),
                ("案例类型", selected_case_summary["case_id"]),
                ("案例锚点", selected_case_summary["case_anchor"]),
                ("case_key", selected_case_summary["case_key"]),
                ("变更类型", selected_case_summary["change_types"]),
                ("待增加", f"{selected_case_summary['add_count']} 条"),
                ("待删除", f"{selected_case_summary['remove_count']} 条"),
                ("待更新", f"{selected_case_summary['changed_count']} 对"),
            ],
            tone="amber",
            key=f"incremental_case_detail_{selected_case_summary['case_key']}",
            default=False,
        )
        if selected_case_detail["case_marker"]:
            st.info("该案例是新案例，将作为整案新增。")
        else:
            st.caption("当前案例若存在同名重复项，后端会先在同一案例锚点组内按事实重叠度匹配最像的一项，再计算增量。")

    with overview_col2:
        render_section_header("增量关系图", "按待增加、待删除、逻辑变更三类分开展示。")
        st.caption(
            f"上方统计是当前领域原始 pending 总量；下方图谱只展示当前选中案例的去重后变更。"
        )
        graph_config = Config(
            width=860,
            height=420,
            directed=True,
            physics=True,
            hierarchical=False,
            nodeHighlightBehavior=True,
            highlightColor="#F6E05E",
        )
        graph_tab_add, graph_tab_remove, graph_tab_changed = st.tabs(["待增加图谱", "待删除图谱", "逻辑变更图谱"])
        with graph_tab_add:
            add_nodes, add_edges = build_incremental_category_graph(selected_case_summary, selected_case_detail, "add")
            if add_nodes:
                agraph(nodes=add_nodes, edges=add_edges, config=graph_config)
            else:
                st.caption("当前案例没有待增加图谱。")
        with graph_tab_remove:
            remove_nodes, remove_edges = build_incremental_category_graph(selected_case_summary, selected_case_detail, "remove")
            if remove_nodes:
                agraph(nodes=remove_nodes, edges=remove_edges, config=graph_config)
            else:
                st.caption("当前案例没有待删除图谱。")
        with graph_tab_changed:
            changed_nodes, changed_edges = build_incremental_category_graph(selected_case_summary, selected_case_detail, "changed")
            if changed_nodes:
                agraph(nodes=changed_nodes, edges=changed_edges, config=graph_config)
            else:
                st.caption("当前案例没有逻辑变更图谱。")

    render_section_header("三类增量明细", "按案例查看新增、删除与逻辑变更的详细记录。")
    tab_add, tab_remove, tab_changed = st.tabs(["待增加", "待删除", "逻辑更新对"])

    with tab_add:
        add_df = flatten_incremental_records(selected_case_detail["add_records"])
        if not add_df.empty:
            st.dataframe(add_df[["row", "case_name", "head", "relation", "tail", "fact_hash"]], width='stretch', hide_index=True)
        else:
            st.caption("当前案例无待增加三元组。")
        with st.expander("查看待增加 JSON"):
            st.json(selected_case_detail["add_records"])

    with tab_remove:
        remove_df = flatten_incremental_records(selected_case_detail["remove_records"])
        if not remove_df.empty:
            st.dataframe(remove_df[["row", "case_name", "head", "relation", "tail", "fact_hash"]], width='stretch', hide_index=True)
        else:
            st.caption("当前案例无待删除三元组。")
        with st.expander("查看待删除 JSON"):
            st.json(selected_case_detail["remove_records"])

    with tab_changed:
        changed_df = flatten_changed_records(selected_case_detail["changed_records"])
        if not changed_df.empty:
            st.caption("待更新来自 extract.py 的严格配对结果，不等于把所有待删除与待增加记录简单两两组合。")
            st.dataframe(changed_df[["row", "case_name", "relation", "old_head", "old_tail", "new_head", "new_tail"]], width='stretch', hide_index=True)
            for row in changed_df.itertuples(index=False):
                compare_col1, compare_col2 = st.columns(2)
                with compare_col1:
                    render_diff_triplet_card("旧逻辑", f"({row.old_head}, {row.relation}, {row.old_tail})", tone="red")
                with compare_col2:
                    render_diff_triplet_card("新逻辑", f"({row.new_head}, {row.relation}, {row.new_tail})", tone="green")
        else:
            st.caption("当前案例无待更新逻辑对。")
        with st.expander("查看逻辑更新对 JSON"):
            st.json(selected_case_detail["changed_records"])

    render_section_header("处理日志", "记录几点完成了什么操作，并保留关键输出信息。")
    log_col1, log_col2 = st.columns([1.05, 1.35])
    with log_col1:
        render_operation_history("incremental_operation_history", "暂时还没有操作记录。")
    with log_col2:
        combined_logs = st.session_state.incremental_last_logs or [
            f"[{current_log_timestamp()}] 当前领域：{bundle['domain_name']}",
            f"  - 目录：{bundle['domain_dir']}",
            f"  - 汇总：add={add_triple_count}, remove={len(bundle['pending_remove'])}, changed={len(bundle['pending_changed'])}",
        ]
        st.code("\n".join(combined_logs), language="text")


# ═══════════════════════════════════════════════════════════════════
# NHTSA 工作台 (from agentic_kg/main.py)
# ═══════════════════════════════════════════════════════════════════

def _nhtsa_load_csv(name: str):
    path = NHTSA_DATA_DIR / name
    if not path.exists():
        return None
    return pd.read_csv(path)


def render_nhtsa_dashboard() -> None:
    rs = _nhtsa_load_csv("risk_scenarios.csv")
    kg = _nhtsa_load_csv("kg_triples.csv")
    tc = _nhtsa_load_csv("test_cases.csv")
    vehicles = _nhtsa_load_csv("vehicles.csv")
    complaints = _nhtsa_load_csv("complaints.csv")
    recalls = _nhtsa_load_csv("recalls.csv")

    if rs is None:
        st.warning("未找到 NHTSA 数据文件。请先在项目目录运行：`python nhtsa_mvp.py` 然后 `python build_kg_and_tests.py`")
        return

    n_veh = vehicles["vehicle_key"].nunique() if vehicles is not None else rs["vehicle_key"].nunique()
    n_comp = len(complaints) if complaints is not None else 0
    n_rec = len(recalls) if recalls is not None else 0
    n_kg = len(kg) if kg is not None else 0
    n_tc = len(tc) if tc is not None else 0

    ev_count = 9; ice_count = n_veh - ev_count if vehicles is not None else 0

    st.markdown(
        f"""
        <div class="nhtsa-hero">
          <div class="nhtsa-hero-title">NHTSA 车辆安全风险数据工作台</div>
          <div class="nhtsa-hero-sub">
            基于美国 NHTSA 公开 API 自动采集 {n_veh} 款车型的召回、投诉数据，
            构建知识图谱三元组，智能生成工程化测试用例。
            <span class="nhtsa-tag ev">纯电 × 9</span>
            <span class="nhtsa-tag ice">燃油/混动 × {ice_count}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="nhtsa-metric-row">
          <div class="nhtsa-metric"><div class="nhtsa-metric-value accent">{n_veh}</div><div class="nhtsa-metric-label">车型覆盖</div></div>
          <div class="nhtsa-metric"><div class="nhtsa-metric-value warn">{n_comp:,}</div><div class="nhtsa-metric-label">投诉记录</div></div>
          <div class="nhtsa-metric"><div class="nhtsa-metric-value">{n_rec:,}</div><div class="nhtsa-metric-label">召回记录</div></div>
          <div class="nhtsa-metric"><div class="nhtsa-metric-value good">{n_kg:,}</div><div class="nhtsa-metric-label">KG 三元组</div></div>
          <div class="nhtsa-metric"><div class="nhtsa-metric-value accent">{n_tc:,}</div><div class="nhtsa-metric-label">测试用例</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c_left, c_right = st.columns([1.2, 1])
    with c_left:
        st.markdown('<div class="nhtsa-panel"><div class="nhtsa-panel-title">Top 10 高优先级风险场景</div>', unsafe_allow_html=True)
        top10 = rs.head(10)
        max_p = top10["priority_score"].max()
        for _, r in top10.iterrows():
            pct = r["priority_score"] / max_p * 100 if max_p > 0 else 0
            css_class = "critical" if r["priority_score"] >= 5 else ("high" if r["priority_score"] >= 3 else ("medium" if r["priority_score"] >= 1.5 else "low"))
            st.markdown(
                f"""<div class="risk-bar-row"><div class="risk-bar-label" title="{r['vehicle_key']}">{r['risk_scenario'][:28]}</div><div class="risk-bar-track"><div class="risk-bar-fill {css_class}" style="width:{pct:.0f}%;"></div></div><div class="risk-bar-score">{r['priority_score']:.1f}</div></div>""",
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

    with c_right:
        st.markdown('<div class="nhtsa-panel"><div class="nhtsa-panel-title">风险场景分布</div>', unsafe_allow_html=True)
        dist = rs["risk_scenario"].value_counts().head(12)
        total = dist.sum()
        for scenario, count in dist.items():
            pct = count / total * 100
            label = scenario.replace("_", " ")[:30]
            st.markdown(f"""<div class="risk-bar-row"><div class="risk-bar-label" style="width:160px;">{label}</div><div class="risk-bar-track"><div class="risk-bar-fill medium" style="width:{pct:.0f}%;"></div></div><div class="risk-bar-score" style="width:60px;">{count} ({pct:.0f}%)</div></div>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("车型风险对比", expanded=False):
        if vehicles is not None:
            v_data = []
            for vk in vehicles["vehicle_key"]:
                sub = rs[rs["vehicle_key"] == vk]
                if sub.empty: continue
                v_data.append({"车型": vk, "场景数": len(sub), "总证据": sub["evidence_count"].sum(), "最高优先级": round(sub["priority_score"].max(), 2), "首要风险": sub.iloc[0]["risk_scenario"].replace("_", " ")[:30]})
            if v_data:
                st.dataframe(pd.DataFrame(v_data), width='stretch', hide_index=True)

    with st.expander("知识图谱统计", expanded=False):
        if kg is not None:
            rel_dist = kg["relation"].value_counts()
            tag_classes = ["r1", "r2", "r3", "r4", "r5", "r6"]
            tags_html = " ".join(f'<span class="rel-tag {tag_classes[i % 6]}">{rel} &nbsp;{cnt:,}</span>' for i, (rel, cnt) in enumerate(rel_dist.items()))
            st.markdown(f'<div class="nhtsa-panel"><div class="nhtsa-panel-title">关系类型分布</div>{tags_html}</div>', unsafe_allow_html=True)
            st.caption("样例行（前 5 行）")
            st.dataframe(kg.head(5)[["head", "relation", "tail", "vehicle_key"]], width='stretch', hide_index=True)

    with st.expander("工程化测试用例预览", expanded=False):
        if tc is not None and len(tc) > 0:
            st.caption(f"共 {len(tc)} 条，按 priority_score 降序。展示前 5 条。")
            for i, (_, row) in enumerate(tc.head(5).iterrows(), 1):
                with st.container():
                    st.markdown(f"**{i}. {row['test_case_id']} — {row['test_case_title']}**")
                    c1, c2, c3 = st.columns(3)
                    c1.caption(f"车型: {row['vehicle_key']}")
                    c2.caption(f"风险: {row['risk_scenario']}")
                    c3.caption(f"优先级: {row['priority_score']}")
                    with st.expander(f"查看详情 #{i}", expanded=False):
                        st.caption(f"**测试环境:** {row['test_environment']}")
                        st.caption(f"**前置条件:** {row['preconditions']}")
                        st.caption(f"**测试步骤:** {row['test_steps']}")
                        st.caption(f"**观测信号:** {str(row.get('observed_signals', ''))[:200]}")
                        st.caption(f"**通过标准:** {str(row.get('pass_fail_criteria', ''))[:300]}")


# ═══════════════════════════════════════════════════════════════════
# Skills 控制台 (from agentic_kg/main.py)
# ═══════════════════════════════════════════════════════════════════

def load_skill_registry():
    if not SKILL_REGISTRY_PATH.exists():
        return []
    return json.loads(SKILL_REGISTRY_PATH.read_text(encoding="utf-8"))


def load_pending_skill_files():
    if not PENDING_SKILLS_ROOT.exists():
        return []
    return sorted(PENDING_SKILLS_ROOT.glob("*.SKILL.md"), key=lambda p: p.stat().st_mtime, reverse=True)


def render_skills_console() -> None:
    st.markdown("### Skills 自进化控制台")
    st.caption("正式技能只读展示；未知模板只生成 pending 草稿，等待人工审核后再启用。")

    registry = load_skill_registry()
    if registry:
        st.markdown(f"#### 正式 Skill Registry（{len(registry)} 个）")
        cols = st.columns(2)
        for index, skill in enumerate(registry):
            with cols[index % 2]:
                st.markdown(
                    f"""<div class="skill-card"><div class="skill-id">{skill.get('skill_id', '')}</div><div class="skill-name">{skill.get('name', '')}</div><div class="skill-desc">类型：{skill.get('file_type', '')} | 模板：{skill.get('template_kind', '')} | 状态：{skill.get('status', '')}</div><div class="skill-desc">{skill.get('description', '')}</div></div>""",
                    unsafe_allow_html=True,
                )
    else:
        st.warning("没有找到正式技能注册表。")

    # ── 工程师手动创建 Skill ──
    with st.expander("新增 Skill（手动创建）", expanded=False):
        st.caption("请按统一结构填写。参考已有 Skill 的格式以保证一致性。")
        registry = load_skill_registry()
        existing_domains = sorted(set(s.get("template_kind", "") for s in registry if s.get("template_kind")))
        existing_tools = sorted(set(s.get("tool", "") for s in registry if s.get("tool")))
        existing_file_types = sorted(set(s.get("file_type", "") for s in registry if s.get("file_type")))

        new_id = st.text_input("Skill ID *", placeholder="如 excel.my_template.v1", key="new_skill_id",
                               help="格式: {file_type}.{template_kind}.v1")
        new_name = st.text_input("名称 *", placeholder="如 自定义模板 Excel 抽取", key="new_skill_name")

        c1, c2 = st.columns(2)
        ft_options = existing_file_types if existing_file_types else ["excel", "pdf", "fusion", "incremental"]
        new_ft = c1.selectbox("文件类型", ft_options, key="new_skill_ft")
        tk_options = existing_domains + ["（自定义...）"] if existing_domains else ["（自定义...）"]
        tk_sel = c2.selectbox("模板标识 (template_kind)", tk_options, key="new_skill_tk_sel")
        if tk_sel == "（自定义...）":
            new_tk = st.text_input("自定义模板标识", placeholder="如 custom_template", key="new_skill_tk_custom")
        else:
            new_tk = tk_sel

        tool_options = existing_tools + ["（自定义...）"] if existing_tools else ["（自定义...）"]
        tool_sel = st.selectbox("工具函数", tool_options, key="new_skill_tool_sel")
        if tool_sel == "（自定义...）":
            new_tool = st.text_input("自定义工具函数", placeholder="如 extractor.build_xxx_output_lines", key="new_skill_tool_custom")
        else:
            new_tool = tool_sel

        new_desc = st.text_area("描述 *", placeholder="描述适用场景、表头特征、抽取策略...", key="new_skill_desc")
        if st.button("创建 Skill 草稿", key="create_skill_draft", type="primary"):
            if new_id and new_name and new_desc:
                dp = PENDING_SKILLS_ROOT / f"{new_id}.SKILL.md"
                if dp.exists():
                    st.warning(f"已存在: {dp.name}")
                else:
                    dp.parent.mkdir(parents=True, exist_ok=True)
                    draft = f"# Pending Skill: {new_name}\\n- skill_id: {new_id}\\n- file_type: {new_ft}\\n- template_kind: {new_tk}\\n- tool: {new_tool}\\n- status: pending_review\\n- created_by: engineer\\n\\n## Description\\n{new_desc}\\n\\n## 待确认\\n- 字段映射\\n- 抽取策略\\n- 是否沉淀为正式 Skill\\n"
                    dp.write_text(draft, encoding="utf-8")
                    st.success(f"已创建: {dp.name}")
                    st.rerun()
            else:
                st.warning("请填写 Skill ID、名称和描述。")

    pending = load_pending_skill_files()
    st.markdown("#### Pending Skill Drafts")
    if not pending:
        st.info("暂无待审核草稿。上传未知 Excel 模板后自动生成，或通过上方表单手动创建。")
    for path in pending[:10]:
        with st.expander(path.name, expanded=False):
            st.caption(str(path))
            st.markdown(path.read_text(encoding="utf-8", errors="ignore"))
            if st.button("删除此草稿", key=f"del_{path.stem}"):
                path.unlink()
                st.success(f"已删除: {path.name}")
                st.rerun()


def render_agent_os_tab() -> None:
    st.markdown("### 多智能体运行时总览")
    registry = load_skill_registry()
    pending = load_pending_skill_files()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("已注册 Skills", len(registry))
    m2.metric("待审核草稿", len(pending))
    m3.metric("NHTSA 数据", "已就绪" if (NHTSA_DATA_DIR / "risk_scenarios.csv").exists() else "未采集")
    m4.metric("运行环境", "7.27 交付版")
    st.markdown("#### 智能体协作流程")
    agent_cols = st.columns(5)
    agent_items = [
        ("Profiler", "画像输入结构与历史命中"),
        ("Router", "选择正式 Skill 或草稿流"),
        ("Extractor", "调用确定性工具链抽取"),
        ("Reviewer", "质量审阅与风险归因"),
        ("Curator", "生成待审核 Skill 草稿"),
    ]
    for col, (title, body) in zip(agent_cols, agent_items):
        col.markdown(f"""<div style="border:1px solid #dbe3ef;border-radius:8px;padding:10px 8px;background:#f8fafc;min-height:70px;"><div style="color:#0f172a;font-size:0.86rem;font-weight:800;">{title}</div><div style="color:#64748b;font-size:0.78rem;">{body}</div></div>""", unsafe_allow_html=True)


# --- UI LAYOUT ---

inject_global_styles()
render_hero_banner(
    "车辆知识图谱工作台 · 智己项目",
    "Excel 三元组抽取 · PDF 表格结构理解 · NHTSA 车辆安全风险工作台 · Skills 自进化闭环",
    "🧩",
)

tab_excel, tab_pdf, tab_nhtsa, tab_incremental, tab_skills, tab_agentos = st.tabs([
    "📗 Excel 图谱工作台", "📘 PDF KG 工作台", "🚗 NHTSA 工作台", "📙 增量更新", "🧠 Skills 进化", "⚙️ Agent OS"
])

with tab_excel:
    render_excel_workbench()

with tab_pdf:
    render_pdf_workbench()

with tab_nhtsa:
    render_nhtsa_dashboard()

with tab_incremental:
    render_incremental_workbench()

with tab_skills:
    render_skills_console()

with tab_agentos:
    render_agent_os_tab()


