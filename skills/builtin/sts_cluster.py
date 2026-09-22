import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from llm_client import generate_testcase

from ..base import BaseSkill
from .sts_text import compact_text, normalize_mojibake, write_jsonl


class STSClusterTopicsSkill(BaseSkill):
    name = "sts.cluster_topics"
    description = "Cluster STS requirement units into test-generation topics."
    input_schema = {"required": [], "optional": ["document_id", "sections", "requirement_units", "mineru_artifacts", "model"]}
    output_schema = {"format": "topic_clusters"}

    TOPIC_RULES = [
        ("hmi_warning", "HMI warnings and chime/icon alerts", ("TT", "Warning", "Chime", "报警音", "文字弹框", "图标显示", "HMI", "仪表", "中控屏", "常显")),
        ("remote_control", "Mobile app remote tailgate control", ("APP", "远程", "手机", "静默解锁", "remote")),
        ("switch_control", "Tailgate button and hard-switch control", ("按键", "硬开关", "外开关", "内开关", "尾门开关", "中控", "开关控制")),
        ("motion_control", "Tailgate open/close motion control", ("打开", "关闭", "开启", "停止", "运动", "高度", "洗车模式", "防夹")),
        ("vehicle_state", "Vehicle state and preconditions", ("电源", "车速", "档位", "P档", "整车模式", "低电量", "KL15", "OFF")),
        ("failure_handling", "Failure reminders and exception handling", ("失败", "异常", "无效", "拒绝", "不满足", "Fail", "Invalid", "DTC")),
        ("signal_interface", "Signals and service interfaces", ("Signal", "CAN", "LIN", "SOA", "接口", "信号", "报文", "parameter", "PwrLftgt")),
        ("priority_arbitration", "Service priority and arbitration", ("优先级", "仲裁", "占用", "priority", "occupy")),
    ]

    def run(self, input_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        document_id = input_data.get("document_id") or ""
        sections = [self._prepare_section(sec) for sec in (input_data.get("sections") or [])]
        units = [self._prepare_unit(unit) for unit in (input_data.get("requirement_units") or [])]
        artifacts = input_data.get("mineru_artifacts") or {}

        items = units or sections
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        names: Dict[str, str] = {}
        for item in items:
            topic_id, topic_name = self._classify(item)
            group_id = self._group_id(item, topic_id, bool(units))
            grouped[group_id].append(item)
            names[group_id] = self._group_name(item, topic_name, bool(units))

        clusters = []
        for index, (topic_id, cluster_items) in enumerate(grouped.items(), 1):
            requirement_units = cluster_items if units else []
            section_refs = self._section_refs(cluster_items, sections)
            clusters.append({
                "cluster_id": f"topic_{index:02d}_{topic_id}",
                "topic_id": topic_id,
                "topic": names.get(topic_id, "General functional requirements"),
                "summary": self._summary(cluster_items),
                "section_count": len(section_refs),
                "unit_count": len(requirement_units),
                "page_start": self._min_page(cluster_items),
                "page_end": self._max_page(cluster_items),
                "sections": section_refs,
                "requirement_units": requirement_units,
                "keywords": self._keywords(cluster_items),
                "test_intents": self._intents(cluster_items),
                "source_quality": self._cluster_quality(cluster_items),
            })

        clusters.sort(key=lambda item: (item.get("page_start") or 999999, item.get("cluster_id", "")))
        if os.getenv("STS_LLM_REFINE_CLUSTERS", "").lower() in {"1", "true", "yes"}:
            clusters = self._refine_with_llm(clusters, input_data.get("model") or os.getenv("STS_CLUSTER_MODEL", "Qwen3-32B"))
        artifacts_paths = self._save_artifacts(artifacts, clusters)
        return {"document_id": document_id, "topic_clusters": clusters, "cluster_artifacts": artifacts_paths, "skill": self.name}

    def _prepare_section(self, section: Dict[str, Any]) -> Dict[str, Any]:
        item = dict(section)
        item["title"] = compact_text(normalize_mojibake(item.get("title", "")))
        item["content"] = compact_text(normalize_mojibake(item.get("content", "")))
        item["content_preview"] = item["content"][:260]
        item.setdefault("source_kind", "section")
        return item

    def _prepare_unit(self, unit: Dict[str, Any]) -> Dict[str, Any]:
        item = dict(unit)
        for key, value in list(item.items()):
            if isinstance(value, str):
                item[key] = compact_text(normalize_mojibake(value))
        item["title"] = item.get("function") or item.get("section_title") or item.get("section_id", "")
        item["content"] = compact_text(" ".join(str(item.get(field, "")) for field in (
            "preconditions", "triggers", "actions", "expected_results", "hmi_display", "status_feedback", "remarks"
        )))
        item["content_preview"] = item["content"][:260]
        item.setdefault("source_kind", "requirement_unit")
        return item

    def _classify(self, item: Dict[str, Any]) -> tuple[str, str]:
        text = f"{item.get('title', '')}\n{item.get('content', '')}".lower()
        scores = []
        for topic_id, topic_name, keywords in self.TOPIC_RULES:
            score = sum(text.count(keyword.lower()) for keyword in keywords)
            if score:
                scores.append((score, topic_id, topic_name))
        if scores:
            scores.sort(key=lambda row: (-row[0], row[1]))
            return scores[0][1], scores[0][2]
        if re.search(r"变更|版本|目录|概述", item.get("title", ""), re.I):
            return "document_meta", "Document metadata and version info"
        return "general", "General functional requirements"

    def _group_id(self, item: Dict[str, Any], topic_id: str, by_unit: bool) -> str:
        if not by_unit:
            return topic_id
        section_id = str(item.get("section_id") or "unknown")
        safe_section = re.sub(r"[^0-9A-Za-z_.-]+", "_", section_id).strip("_") or "unknown"
        return f"{safe_section}_{topic_id}"

    def _group_name(self, item: Dict[str, Any], topic_name: str, by_unit: bool) -> str:
        if not by_unit:
            return topic_name
        section_id = item.get("section_id") or ""
        title = item.get("section_title") or item.get("title") or "General functional requirements"
        return compact_text(f"{section_id} {title} ({topic_name})")

    def _section_refs(self, items: List[Dict[str, Any]], sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        section_by_id = {sec.get("section_id"): sec for sec in sections}
        refs: Dict[str, Dict[str, Any]] = {}
        for item in items:
            sid = item.get("section_id")
            if not sid:
                continue
            sec = section_by_id.get(sid, {})
            refs[sid] = {
                "section_id": sid,
                "title": item.get("section_title") or sec.get("title") or item.get("title", ""),
                "page_start": item.get("page_start") or sec.get("page_start"),
                "page_end": item.get("page_end") or sec.get("page_end"),
                "content_preview": sec.get("content_preview") or item.get("content_preview") or "",
            }
        return list(refs.values())

    def _summary(self, items: List[Dict[str, Any]]) -> str:
        return "；".join(
            compact_text(f"{item.get('section_id', '')} {item.get('title', '')}") for item in items[:5]
        )

    def _keywords(self, items: List[Dict[str, Any]]) -> List[str]:
        text = " ".join(f"{item.get('title', '')} {item.get('content_preview', '')}" for item in items)
        words = re.findall(r"[A-Za-z][A-Za-z0-9_.-]{2,}|[\u4e00-\u9fff]{2,8}", text)
        stop = {"功能", "需求", "条件", "执行", "结果", "所有", "适用", "车辆", "状态", "章节"}
        counts: Dict[str, int] = defaultdict(int)
        for word in words:
            if word in stop or word.lower() in stop:
                continue
            counts[word] += 1
        return [word for word, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]]

    def _intents(self, items: List[Dict[str, Any]]) -> List[str]:
        intents = []
        for item in items:
            intents.extend(item.get("test_intents") or [])
        return list(dict.fromkeys(intents))[:10]

    def _cluster_quality(self, items: List[Dict[str, Any]]) -> str:
        qualities = [item.get("source_quality") for item in items]
        if "high" in qualities:
            return "high"
        if "medium" in qualities:
            return "medium"
        return "low"

    def _min_page(self, items: List[Dict[str, Any]]) -> Optional[int]:
        pages = [item.get("page_start") for item in items if isinstance(item.get("page_start"), int)]
        return min(pages) if pages else None

    def _max_page(self, items: List[Dict[str, Any]]) -> Optional[int]:
        pages = [item.get("page_end") for item in items if isinstance(item.get("page_end"), int)]
        return max(pages) if pages else None

    def _refine_with_llm(self, clusters: List[Dict[str, Any]], model: str) -> List[Dict[str, Any]]:
        brief = [{
            "cluster_id": c["cluster_id"],
            "topic": c["topic"],
            "keywords": c["keywords"],
            "summary": c["summary"],
            "unit_count": c["unit_count"],
        } for c in clusters]
        prompt = (
            "You are an automotive STS test analysis expert. Refine only the topic labels from the cluster summaries below. "
            "Do not merge, delete, or add cluster_id values. "
            "Return a JSON array; each item must include cluster_id, topic, and reason.\n"
            f"{json.dumps(brief, ensure_ascii=False, indent=2)}"
        )
        try:
            content, _ = generate_testcase(prompt, model=model, max_tokens=2048)
            data = self._extract_json(content)
            labels = {item["cluster_id"]: item for item in data if isinstance(item, dict) and item.get("cluster_id")}
            for cluster in clusters:
                label = labels.get(cluster["cluster_id"])
                if label and label.get("topic"):
                    cluster["topic"] = compact_text(label["topic"])
                    cluster["llm_label_reason"] = compact_text(label.get("reason", ""))
        except Exception as exc:
            for cluster in clusters:
                cluster["llm_label_error"] = str(exc)
        return clusters

    def _extract_json(self, content: str) -> Any:
        match = re.search(r"\[[\s\S]*\]", content or "")
        if not match:
            return []
        return json.loads(match.group(0))

    def _save_artifacts(self, artifacts: Dict[str, Any], clusters: List[Dict[str, Any]]) -> Dict[str, str]:
        artifact_dir = artifacts.get("artifact_dir")
        if not artifact_dir:
            return {}
        root = Path(artifact_dir)
        paths = {
            "topic_clusters_path": str(root / "topic_clusters.json"),
            "topic_clusters_jsonl_path": str(root / "topic_clusters.jsonl"),
        }
        (root / "topic_clusters.json").write_text(json.dumps(clusters, ensure_ascii=False, indent=2), encoding="utf-8")
        write_jsonl(root / "topic_clusters.jsonl", clusters)
        return paths
