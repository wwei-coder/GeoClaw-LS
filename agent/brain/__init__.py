from .prompt_catalog import BrainPromptCatalog, PromptDefinition, get_prompt_catalog
from .schemas import BrainAnswer, BrainContext, BrainDecision, BrainPlan, BrainPlanStep, BrainReview


def __getattr__(name):
    if name == "LLMBrain":
        from .llm_brain import LLMBrain as _LLMBrain

        return _LLMBrain
    raise AttributeError(name)

__all__ = [
    "LLMBrain",
    "BrainPromptCatalog",
    "PromptDefinition",
    "get_prompt_catalog",
    "BrainContext",
    "BrainPlan",
    "BrainPlanStep",
    "BrainDecision",
    "BrainReview",
    "BrainAnswer",
]
