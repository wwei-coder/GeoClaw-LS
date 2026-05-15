from .prompt_catalog import BrainPromptCatalog, PromptDefinition, get_prompt_catalog
from .schemas import BrainAnswer, BrainContext, BrainDecision, BrainPlan, BrainPlanStep, BrainReview

def __getattr__(name):
    if name == "LLMBrain":
        from .llm_brain import LLMBrain as _LLMBrain

        return _LLMBrain
    if name == "PlannerService":
        from .planning import PlannerService as _PlannerService

        return _PlannerService
    if name == "SmallTalkService":
        from .smalltalk import SmallTalkService as _SmallTalkService

        return _SmallTalkService
    if name == "HeuristicDecisionService":
        from .decision import HeuristicDecisionService as _HeuristicDecisionService

        return _HeuristicDecisionService
    if name == "AnswerSynthesisService":
        from .synthesis import AnswerSynthesisService as _AnswerSynthesisService

        return _AnswerSynthesisService
    raise AttributeError(name)

__all__ = [
    "LLMBrain",
    "BrainPromptCatalog",
    "PromptDefinition",
    "get_prompt_catalog",
    "HeuristicDecisionService",
    "PlannerService",
    "BrainContext",
    "BrainPlan",
    "BrainPlanStep",
    "BrainDecision",
    "BrainReview",
    "BrainAnswer",
    "AnswerSynthesisService",
    "SmallTalkService",
]
