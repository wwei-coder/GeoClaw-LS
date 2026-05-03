from __future__ import annotations
import asyncio
from agent.brain import BrainAnswer, BrainContext, BrainDecision, BrainPlan, BrainReview, LLMBrain

class _StubPlannerChain:
    async def ainvoke(self, inputs):
        return {
            "plan": {"steps": [{"tool": "RAG", "task": inputs["question"]}]},
            "trace": "Planner: 1 steps",
        }

class _StubDecisionChain:
    async def ainvoke(self, _inputs):
        return {
            "force_tool": None,
            "final_use_kb": True,
            "context_score": 0.72,
            "trace": "Decision: use_kb=True, force=None",
        }

class _StubSynthesisChain:
    async def ainvoke(self, _inputs):
        return {"final_answer": "综合回答", "final_sources": ["doc-a.pdf"]}

class _StubQAChain:
    def __init__(self, answer: str):
        self._answer = answer

    async def ainvoke(self, _inputs):
        return {"answer": self._answer, "confidence": 0.0, "sources": []}

class _DummyAgentCore:
    async def _fix_terminology_async(self, answer: str, question: str = "") -> str:
        return f"{answer}|{question}"


async def _review_llm_pass(_prompt: str) -> str:
    return '{"status":"PASS","reason":"","suggestion":""}'

def test_brain_schemas_instantiation():
    ctx = BrainContext(question="q", session_id=1, file_id="f1")
    plan = BrainPlan(steps=[{"tool": "RAG", "task": "q"}], raw_plan={"steps": []}, source="PlannerChain")
    decision = BrainDecision(force_tool="RAG", need_kb=True, context_score=0.5, reason="ok")
    review = BrainReview(is_satisfactory=True, feedback="", review_count=1)
    answer = BrainAnswer(answer="a", confidence_score=0.8, confidence_label="高", sources=["doc"])

    assert ctx.question == "q"
    assert plan.source == "PlannerChain"
    assert decision.need_kb is True
    assert review.review_count == 1
    assert answer.confidence_label == "高"

def test_llm_brain_thin_wrappers_plan_decide_synthesize_review():
    brain = LLMBrain(
        _DummyAgentCore(),
        planner_chain=_StubPlannerChain(),
        decision_chain=_StubDecisionChain(),
        synthesis_chain=_StubSynthesisChain(),
        small_talk_chain=_StubQAChain("闲聊回复"),
        memory_query_chain=_StubQAChain("记忆回复"),
        review_llm_call=_review_llm_pass,
    )

    plan = asyncio.run(brain.plan("测试问题"))
    assert plan.steps[0]["tool"] == "RAG"

    decision = asyncio.run(brain.decide("测试问题", {"steps": []}))
    assert decision.need_kb is True
    assert decision.context_score > 0

    syn = asyncio.run(
        brain.synthesize(
            question="测试问题",
            step_results=["[RAG] x"],
            kb_chunks=[],
            sources=["doc-a.pdf"],
            canceled=False,
        )
    )
    assert syn.answer == "综合回答"
    assert syn.sources == ["doc-a.pdf"]

    review = asyncio.run(brain.review(question="q", answer="a", review_count=0))
    assert review.is_satisfactory is True

    normalized = asyncio.run(brain.normalize_answer_terms("答复", "问题"))
    assert normalized == "答复|问题"
