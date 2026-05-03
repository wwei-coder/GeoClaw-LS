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
class BrainPlan:
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
