from __future__ import annotations

from agent.brain.prompt_catalog import BrainPromptCatalog
from tools.registry import get_enabled_tool_names


def test_catalog_lists_key_prompts():
    catalog = BrainPromptCatalog()
    ids = set(catalog.list_prompt_ids())
    required = {
        "planner",
        "reviewer",
        "synthesis_final_answer",
        "semantic_rewrite",
        "keyword_expansion",
        "metadata_filter",
        "fix_insar",
    }
    assert required.issubset(ids)


def test_key_prompts_have_metadata_contracts():
    catalog = BrainPromptCatalog()
    for prompt_id in ["planner", "reviewer", "synthesis_final_answer", "semantic_rewrite", "metadata_filter"]:
        definition = catalog.get_definition(prompt_id)
        assert definition.version
        assert definition.description
        assert definition.required_inputs
        assert definition.output_contract


def test_planner_prompt_renders_enabled_tools_without_kg_rag():
    catalog = BrainPromptCatalog()
    rendered = catalog.render("planner", question="滑坡定义是什么")
    for tool_name in get_enabled_tool_names():
        assert f"- {tool_name}" in rendered
    assert "KG_RAG" not in rendered


def test_reviewer_prompt_keeps_pass_fail_contract():
    catalog = BrainPromptCatalog()
    rendered = catalog.render("reviewer", question="q", answer="a")
    assert "PASS" in rendered
    assert "FAIL" in rendered


def test_synthesis_prompt_keeps_evidence_boundaries():
    catalog = BrainPromptCatalog()
    rendered = catalog.render(
        "synthesis_final_answer",
        question="q",
        step_results="s",
        kb_evidence="e",
    )
    assert "资料支持" in rendered
    assert "资料未明确提及" in rendered


def test_insar_constraint_is_explicit_in_catalog_prompt():
    catalog = BrainPromptCatalog()
    rendered = catalog.render("fix_insar", question="InSAR 是什么", answer="...")
    assert "干涉合成孔径雷达（Interferometric Synthetic Aperture Radar）" in rendered


def test_catalog_fallback_is_explicit_when_yaml_missing():
    catalog = BrainPromptCatalog(prompts_data={"prompts": {}}, planner_data={"prompts": {}})
    planner_def = catalog.get_definition("planner")
    reviewer_def = catalog.get_definition("reviewer")
    assert planner_def.fallback_id is not None
    assert planner_def.fallback_reason is not None
    assert reviewer_def.fallback_id is not None
    assert reviewer_def.fallback_reason is not None
