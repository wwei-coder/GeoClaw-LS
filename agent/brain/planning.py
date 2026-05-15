from __future__ import annotations
from typing import Any, Callable, Dict
from agent.brain.planner_parser import process_planner_response
from agent.brain.prompt_catalog import get_prompt_catalog
from utils.logger import logger
from utils.ollama_client import ask_ollama, ask_ollama_async

async def plan_task_async(question: str) -> Dict[str, Any]:
    prompt = get_prompt_catalog().render("planner", question=question)
    raw = await ask_ollama_async(prompt)
    return process_planner_response(raw, question)

def plan_task(question: str) -> Dict[str, Any]:
    prompt = get_prompt_catalog().render("planner", question=question)
    raw = ask_ollama(prompt)
    return process_planner_response(raw, question)

class PlannerService:
    def __init__(
        self,
        *,
        plan_task_fn: Callable[[str], Dict[str, Any]] = plan_task,
        plan_task_async_fn: Callable[[str], Any] = plan_task_async,
    ):
        self.plan_task_fn = plan_task_fn
        self.plan_task_async_fn = plan_task_async_fn

    def handle(self, question: str, output_key: str = "plan") -> Dict[str, Any]:
        plan = self.plan_task_fn(question)
        logger.info("[PlannerChain] 任务计划：")
        for i, s in enumerate(plan["steps"], 1):
            logger.info(f"  {i}. {s['tool']} → {s['task']}")

        trace = f"Planner: {len(plan['steps'])} steps"
        return {output_key: plan, "trace": trace}

    async def handle_async(self, question: str, output_key: str = "plan") -> Dict[str, Any]:
        plan = await self.plan_task_async_fn(question)
        logger.info("[PlannerChain] 任务计划 (Async)：")
        for i, s in enumerate(plan["steps"], 1):
            logger.info(f"  {i}. {s['tool']} → {s['task']}")

        trace = f"Planner: {len(plan['steps'])} steps"
        return {output_key: plan, "trace": trace}
