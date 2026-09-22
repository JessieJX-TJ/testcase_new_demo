import html
import re
from pathlib import Path
from typing import Any


MOJIBAKE_MARKERS = (
    "鐢", "鍔", "绋", "灏", "闂", "犺", "妗", "℃", "€", "�", "浠", "棰", "瑙", "鎵",
)


def compact_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_mojibake(value: Any) -> str:
    """Repair UTF-8 Chinese text that was mistakenly decoded as GBK/GB18030."""
    text = str(value or "")
    if not text:
        return ""
    candidates = [text]
    for encoding in ("gb18030", "gbk"):
        try:
            repaired = text.encode(encoding, errors="strict").decode("utf-8", errors="strict")
            candidates.append(repaired)
        except Exception:
            pass
    return max(candidates, key=_quality_score)


def normalize_deep(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_mojibake(value)
    if isinstance(value, list):
        return [normalize_deep(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_deep(item) for key, item in value.items()}
    return value


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(__import__("json").dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )


def _quality_score(text: str) -> int:
    marker_penalty = sum(text.count(marker) for marker in MOJIBAKE_MARKERS) * 12
    replacement_penalty = text.count("?") + text.count("�") * 20
    useful_hits = sum(text.count(word) for word in (
        "电动", "尾门", "功能", "需求", "前提", "触发", "执行", "预期", "状态", "信号",
        "车辆", "解锁", "关闭", "打开", "测试", "章节", "条件", "异常", "诊断",
    )) * 8
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    return chinese_chars + useful_hits - marker_penalty - replacement_penalty
