from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class BrainContext:
    question: str
    session_id: Optional[int] = None
    file_id: Optional[str] = None
    files: List[Dict[str, Any]] = field(default_factory=list)
    history: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class BrainPlanStep:
    tool: str
    task: str
    reason: str = ""
    expected_output: str = ""
    fallback: str = ""

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "BrainPlanStep":
        data = dict(payload or {})
        return cls(
            tool=str(data.get("tool") or "LLM").upper().strip() or "LLM",
            task=str(data.get("task") or "").strip(),
            reason=str(data.get("reason") or "").strip(),
            expected_output=str(data.get("expected_output") or "").strip(),
            fallback=str(data.get("fallback") or "").strip(),
        )

    def to_dict(self) -> Dict[str, Any]:
        out = {
            "tool": self.tool,
            "task": self.task,
        }
        if self.reason:
            out["reason"] = self.reason
        if self.expected_output:
            out["expected_output"] = self.expected_output
        if self.fallback:
            out["fallback"] = self.fallback
        return out

@dataclass
class BrainPlan:
    intent: str = "mixed"
    need_evidence: bool = False
    risk_level: str = "low"
    answer_requirements: List[str] = field(default_factory=list)
    reasoning_trace: List[Dict[str, str]] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    raw_plan: Dict[str, Any] = field(default_factory=dict)
    source: str = "PlannerChain"
    trace: str = ""

@dataclass
class BrainDecision:
    force_tool: Optional[str] = None
    need_kb: bool = False
    context_score: float = 0.0
    reason: str = ""

@dataclass
class BrainReview:
    is_satisfactory: bool = True
    feedback: str = ""
    review_count: int = 0

@dataclass
class BrainAnswer:
    answer: str = ""
    confidence_score: Optional[float] = None
    confidence_label: Optional[str] = None
    sources: List[str] = field(default_factory=list)
