from core.config import PROMPTS
"""Prompt constants loaded from YAML-first configuration."""

def _prompt(key: str, fallback: str = "") -> str:
    value = PROMPTS.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return fallback

SEMANTIC_REWRITE_PROMPT = _prompt("semantic_rewrite", "用户问题：{question}\n改写查询：")
KEYWORD_EXPANSION_PROMPT = _prompt("keyword_expansion", "用户问题：{question}\n关键词：")
QUERY_EXPANSION_PROMPT = _prompt("query_expansion", KEYWORD_EXPANSION_PROMPT)
SMALL_TALK_PROMPT = _prompt("small_talk", "用户输入：{question}")
FOLLOW_UP_JUDGE_PROMPT = _prompt("follow_up_judge", "【对话摘要】\n{summary}\n【当前问题】\n{question}")
FINAL_ANSWER_PROMPT = _prompt(
    "final_answer",
    "【当前问题】\n{question}\n【工具结果】\n{step_results}\n【可引用资料】\n{kb_evidence}\n### 你的回答",
)
REWRITE_PROMPT = _prompt("rewrite", "【原文】\n{text}\n【全中文改写结果】")
FIX_INSAR_PROMPT = _prompt("fix_insar", "【问题】\n{question}\n【待修正回答】\n{answer}\n【修正后的回答】")
DISCOVERY_PROMPT = _prompt("discovery", "【检索到的文献片段】\n{kb_evidence}\n【探索方向】\n{question}")
CONFIRMATION_JUDGE_PROMPT = _prompt("confirmation_judge", "【最新回复】\n{question}")
REVIEW_PROMPT = _prompt("review", "用户问题：\n{question}\nAgent 回答：\n{answer}")
METADATA_FILTER_PROMPT = _prompt("metadata_filter", "用户：{question}\n输出：")
