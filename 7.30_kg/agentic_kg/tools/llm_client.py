from __future__ import annotations

import json
import os
from typing import Any

from agentic_kg.models import DocumentProfile
from agentic_kg.paths import load_local_env


def _get_openai_client() -> Any:
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:
        raise RuntimeError("openai package is required for LLM-assisted skill drafting.") from exc
    load_local_env()
    api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY/OPENAI_API_KEY is not configured.")
    base_url = os.environ.get("API_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    return OpenAI(api_key=api_key, base_url=base_url, timeout=20.0)


def suggest_skill_draft(profile: DocumentProfile) -> str:
    """Return optional LLM-assisted notes for a pending skill draft.

    The caller is expected to catch exceptions and fall back to deterministic
    drafting because this helper depends on network/API availability.
    """
    client = _get_openai_client()
    model = os.environ.get("AGENT_MODEL_TEXT", "qwen-plus")
    payload = {
        "file_type": profile.file_type,
        "source_name": profile.source_name,
        "sheets": profile.sheets,
        "selected_sheet": profile.selected_sheet,
        "headers": profile.headers,
        "sample_rows": profile.sample_rows[:5],
        "risk_points": profile.risk_points,
    }
    prompt = (
        "你是汽车测试知识图谱抽取系统的 Skill 设计助手。"
        "请根据输入文件画像，给出待审核 Skill 草稿建议。"
        "只输出 Markdown，包含：适用条件、字段映射建议、抽取策略、质量检查建议。"
        "\n\n文件画像：\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return str(response.choices[0].message.content or "").strip()
