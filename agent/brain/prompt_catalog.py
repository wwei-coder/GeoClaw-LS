from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import yaml
import config_runtime as core_config
from tools.registry import render_planner_tool_descriptions

@dataclass
class PromptDefinition:
    prompt_id: str
    version: str
    description: str
    required_inputs: List[str] = field(default_factory=list)
    output_contract: str = ""
    template: str = ""
    source: str = ""

    def render(self, **kwargs: Any) -> str:
        missing = [k for k in self.required_inputs if k not in kwargs]
        if missing:
            raise ValueError(f"[PromptCatalog] prompt={self.prompt_id} 缺少输入参数: {missing}")
        return self.template.format(**kwargs)

class BrainPromptCatalog:
    """Unified prompt catalog with metadata and explicit prompt contracts."""

    def __init__(self, *, prompts_data: Optional[Dict[str, Any]] = None, planner_data: Optional[Dict[str, Any]] = None):
        self._prompts_data = prompts_data if prompts_data is not None else self._load_yaml(core_config.PROMPTS_PATH)
        self._planner_data = planner_data if planner_data is not None else self._load_yaml(core_config.PLANNER_PATH)
        self._defs: Dict[str, PromptDefinition] = {}
        self._build_catalog()

    def list_prompt_ids(self) -> List[str]:
        return sorted(self._defs.keys())

    def get_definition(self, prompt_id: str) -> PromptDefinition:
        key = str(prompt_id or "").strip()
        if key not in self._defs:
            raise KeyError(f"[PromptCatalog] 未知 prompt_id: {key}")
        return self._defs[key]

    def render(self, prompt_id: str, **kwargs: Any) -> str:
        definition = self.get_definition(prompt_id)
        return definition.render(**kwargs)

    # Convenience helpers for current LLMBrain usage.
    def get_review_prompt_template(self) -> str:
        return self.get_definition("reviewer").template

    def render_review_prompt(self, question: str, answer: str) -> str:
        return self.render("reviewer", question=question, answer=answer)

    def _build_catalog(self) -> None:
        planner_template, planner_source = self._resolve_planner_template()
        self._defs["planner"] = PromptDefinition(
            prompt_id="planner",
            version="v1",
            description="任务规划提示词，输出兼容旧格式的结构化 JSON 步骤计划。",
            required_inputs=["question"],
            output_contract=(
                "严格 JSON：兼容 need_kb+steps 旧格式；推荐新增 intent/need_evidence/risk_level/"
                "reasoning_trace/answer_requirements；reasoning_trace 仅允许简短摘要。"
            ),
            template=planner_template,
            source=planner_source,
        )

        def add_prompt(
            *,
            prompt_id: str,
            yaml_key: str,
            version: str,
            description: str,
            required_inputs: List[str],
            output_contract: str,
            source_name: str = "config/prompts.yaml",
        ) -> None:
            template = self._require_prompt_template(yaml_key)
            source = f"{source_name}:prompts.{yaml_key}"
            self._defs[prompt_id] = PromptDefinition(
                prompt_id=prompt_id,
                version=version,
                description=description,
                required_inputs=required_inputs,
                output_contract=output_contract,
                template=template,
                source=source,
            )

        add_prompt(
            prompt_id="small_talk",
            yaml_key="small_talk",
            version="v1",
            description="闲聊与身份说明提示词。",
            required_inputs=["question"],
            output_contract="简短中文回复，保持专业助手定位。",
        )
        add_prompt(
            prompt_id="reviewer",
            yaml_key="review",
            version="v1",
            description="回答审核提示词，要求 PASS/FAIL 兼容输出。",
            required_inputs=["question", "answer"],
            output_contract='JSON，含 status(PASS/FAIL)、reason、suggestion；未来可扩展 action 字段。',
        )
        add_prompt(
            prompt_id="synthesis_final_answer",
            yaml_key="final_answer",
            version="v1",
            description="最终回答综合提示词，强调资料支持边界与引用约束。",
            required_inputs=["question", "step_results", "kb_evidence"],
            output_contract="中文专业回答；按问题复杂度自适应结构；清楚区分资料依据、资料未提及和必要推断，禁止伪造证据。",
        )
        add_prompt(
            prompt_id="semantic_rewrite",
            yaml_key="semantic_rewrite",
            version="v1",
            description="检索语义改写提示词。",
            required_inputs=["question"],
            output_contract="输出单行改写查询，不附加解释。",
        )
        add_prompt(
            prompt_id="keyword_expansion",
            yaml_key="keyword_expansion",
            version="v1",
            description="检索关键词扩展提示词。",
            required_inputs=["question"],
            output_contract="输出关键词文本，用于检索扩展。",
        )
        add_prompt(
            prompt_id="query_expansion",
            yaml_key="query_expansion",
            version="v1",
            description="兼容保留的检索关键词扩展提示词。",
            required_inputs=["question"],
            output_contract="输出关键词文本；当前主检索链路优先使用 keyword_expansion。",
        )
        add_prompt(
            prompt_id="metadata_filter",
            yaml_key="metadata_filter",
            version="v1",
            description="元数据过滤条件提取提示词。",
            required_inputs=["question"],
            output_contract="输出 JSON 过滤条件或空对象。",
        )
        add_prompt(
            prompt_id="follow_up_judge",
            yaml_key="follow_up_judge",
            version="v1",
            description="判断当前问题是否承接对话摘要的提示词。",
            required_inputs=["summary", "question"],
            output_contract="仅输出 YES 或 NO。",
        )
        add_prompt(
            prompt_id="context_relevance",
            yaml_key="context_relevance",
            version="v1",
            description="判断当前问题与对话摘要中地质专业内容相关性的提示词。",
            required_inputs=["summary", "question"],
            output_contract="仅输出 0、0.5 或 1。",
        )
        add_prompt(
            prompt_id="rewrite",
            yaml_key="rewrite",
            version="v1",
            description="滑坡防治领域术语规范化提示词。",
            required_inputs=["text"],
            output_contract="输出滑坡防治语境下术语规范化后的文本；允许保留必要英文缩写、模型名、算法名和专有名词。",
        )
        add_prompt(
            prompt_id="fix_insar",
            yaml_key="fix_insar",
            version="v1",
            description="InSAR 术语与领域边界修正提示词。",
            required_inputs=["question", "answer"],
            output_contract="InSAR 必须解释为干涉合成孔径雷达，禁止错误映射到热红外/光学。",
        )
        add_prompt(
            prompt_id="discovery",
            yaml_key="discovery",
            version="v1",
            description="跨文献交叉洞察提示词。",
            required_inputs=["kb_evidence", "question"],
            output_contract="输出交叉证据、规律与假设，资料不足时明确说明不足。",
        )
        add_prompt(
            prompt_id="confirmation_judge",
            yaml_key="confirmation_judge",
            version="v1",
            description="用户确认意图判定提示词。",
            required_inputs=["question"],
            output_contract="仅输出 YES/NO/UNRELATED。",
        )

    def _resolve_planner_template(self) -> Tuple[str, str]:
        planner_prompt = (((self._planner_data or {}).get("prompts") or {}).get("planner_task") or "").strip()
        if planner_prompt:
            rendered = self._inject_tool_descriptions(planner_prompt)
            return rendered, "config/planner.yaml:prompts.planner_task"
        raise ValueError("[PromptCatalog] config/planner.yaml 缺少必需 prompts.planner_task")

    def _require_prompt_template(self, key: str) -> str:
        value = (((self._prompts_data or {}).get("prompts") or {}).get(key) or "").strip()
        if value:
            return value
        raise ValueError(f"[PromptCatalog] config/prompts.yaml 缺少必需 prompts.{key}")

    def _inject_tool_descriptions(self, template: str) -> str:
        dynamic_tools = render_planner_tool_descriptions()
        if "{tool_descriptions}" in template:
            return template.replace("{tool_descriptions}", dynamic_tools)
        return (
            f"{template}\n\n"
            "【当前启用工具（由统一 registry 动态注入）】\n"
            f"{dynamic_tools}\n"
        )

    def _load_yaml(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                if isinstance(loaded, dict):
                    return loaded
        except Exception:
            return {}
        return {}

_GLOBAL_PROMPT_CATALOG: Optional[BrainPromptCatalog] = None

def get_prompt_catalog(*, force_reload: bool = False) -> BrainPromptCatalog:
    global _GLOBAL_PROMPT_CATALOG
    if _GLOBAL_PROMPT_CATALOG is None or force_reload:
        _GLOBAL_PROMPT_CATALOG = BrainPromptCatalog()
    return _GLOBAL_PROMPT_CATALOG
