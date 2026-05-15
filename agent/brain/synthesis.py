from __future__ import annotations
from typing import Any, Dict, List, Optional
from config_runtime import MAX_CONTEXT_LEN, SYNTHESIS_MAX_EVIDENCE_CHARS
from utils.ollama_client import ask_ollama, ask_ollama_async, ask_ollama_stream, ask_ollama_stream_async
from .prompt_catalog import get_prompt_catalog

class AnswerSynthesisService:
    def __init__(
        self,
        *,
        agent_core: Any,
        memory_service: Any,
        prompt_catalog: Any = None,
        ask_fn=ask_ollama,
        ask_async_fn=ask_ollama_async,
        ask_stream_fn=ask_ollama_stream,
        ask_stream_async_fn=ask_ollama_stream_async,
    ):
        self.agent_core = agent_core
        self.memory_service = memory_service
        self.prompt_catalog = prompt_catalog or get_prompt_catalog()
        self.ask_fn = ask_fn
        self.ask_async_fn = ask_async_fn
        self.ask_stream_fn = ask_stream_fn
        self.ask_stream_async_fn = ask_stream_async_fn

    def _shrink_text_preserve_edges(self, text: str, budget: int) -> str:
        if budget <= 0:
            return ""
        if len(text) <= budget:
            return text
        if budget <= 12:
            return text[:budget]
        marker = "\n...（已压缩中间内容）...\n"
        if budget <= len(marker) + 2:
            return text[: budget - 1] + "…"
        remain = budget - len(marker)
        head_len = remain // 2
        tail_len = remain - head_len
        shrunk = text[:head_len] + marker + text[-tail_len:]
        if len(shrunk) > budget:
            shrunk = shrunk[:budget]
        return shrunk

    def _compress_step_results_for_context(self, step_results: List[str]) -> str:
        if not step_results:
            return ""
        full_steps = "\n".join(step_results)
        full_len = len(full_steps)
        if full_len <= MAX_CONTEXT_LEN:
            return full_steps

        raw_steps = [s if isinstance(s, str) else str(s) for s in step_results]
        n = len(raw_steps)
        sep_total = max(0, n - 1)
        content_budget = max(1, MAX_CONTEXT_LEN - sep_total)
        lengths = [len(s) for s in raw_steps]
        total_len = sum(lengths)
        if total_len <= content_budget:
            return full_steps

        min_each = 80
        if content_budget < n * min_each:
            min_each = max(1, content_budget // n)

        allocs = [min_each for _ in raw_steps]
        remaining = content_budget - sum(allocs)

        if remaining > 0:
            residuals = [max(0, length - min_each) for length in lengths]
            residual_total = sum(residuals)
            if residual_total > 0:
                extras = []
                used = 0
                for idx, r in enumerate(residuals):
                    extra = int(remaining * (r / residual_total))
                    extra = min(extra, r)
                    extras.append(extra)
                    used += extra
                allocs = [a + e for a, e in zip(allocs, extras)]
                remaining -= used
                if remaining > 0:
                    order = sorted(range(n), key=lambda i: residuals[i] - extras[i], reverse=True)
                    for idx in order:
                        if remaining <= 0:
                            break
                        if allocs[idx] < lengths[idx]:
                            allocs[idx] += 1
                            remaining -= 1
            if remaining > 0:
                order = sorted(range(n), key=lambda i: lengths[i], reverse=True)
                for idx in order:
                    if remaining <= 0:
                        break
                    if allocs[idx] < lengths[idx]:
                        allocs[idx] += 1
                        remaining -= 1

        compressed_steps = [self._shrink_text_preserve_edges(step, alloc) for step, alloc in zip(raw_steps, allocs)]
        compressed = "\n".join(compressed_steps)
        if len(compressed) > MAX_CONTEXT_LEN:
            compressed = self._shrink_text_preserve_edges(compressed, MAX_CONTEXT_LEN)
        return compressed

    def _build_kb_evidence(self, kb_chunks: List[Dict[str, Any]]) -> str:
        if not kb_chunks:
            return ""
        lines = []
        for c in kb_chunks:
            content = c.get("content", "") or ""
            if len(content) > SYNTHESIS_MAX_EVIDENCE_CHARS:
                content = content[:SYNTHESIS_MAX_EVIDENCE_CHARS] + "…"
            lines.append(f"【{c.get('doc_name')}】\n{content}")
        return "\n\n".join(lines)

    def _filter_sources_by_citation(self, final_answer: str, sources: List[str]) -> List[str]:
        if not sources:
            return list(sources or [])
        cited = [s for s in sources if s and s in final_answer]
        return cited if cited else list(sources)

    def synthesize(
        self,
        *,
        question: str,
        step_results: List[str],
        kb_chunks: List[Dict[str, Any]],
        sources: List[str],
        stream_callback: Optional[Any] = None,
        canceled: bool = False,
        persist_memory: bool = True,
    ) -> Dict[str, Any]:
        if canceled:
            return {"final_answer": "已取消", "final_sources": []}

        kb_evidence = self._build_kb_evidence(kb_chunks)
        full_steps = self._compress_step_results_for_context(step_results)
        user_prefs_str = self.memory_service.render_user_preferences_block()

        final_prompt = self.prompt_catalog.render(
            "synthesis_final_answer",
            question=question,
            step_results=full_steps,
            kb_evidence=kb_evidence + user_prefs_str,
        )

        final_answer = ""
        if stream_callback:
            cancel_event = getattr(self.agent_core, "_active_cancel_event", None)
            for token in self.ask_stream_fn(final_prompt, temperature=self.agent_core.temperature, cancel_event=cancel_event):
                final_answer += token
                stream_callback(token)
        else:
            final_answer = self.ask_fn(final_prompt, temperature=self.agent_core.temperature).strip()

        final_answer = self.agent_core._fix_terminology(final_answer, question)
        final_sources = self._filter_sources_by_citation(final_answer, list(sources or []))
        if persist_memory:
            self.memory_service.apply_post_answer_effects(question, final_answer)
        return {"final_answer": final_answer, "final_sources": final_sources}

    async def synthesize_async(
        self,
        *,
        question: str,
        step_results: List[str],
        kb_chunks: List[Dict[str, Any]],
        sources: List[str],
        stream_callback: Optional[Any] = None,
        canceled: bool = False,
        persist_memory: bool = True,
    ) -> Dict[str, Any]:
        if canceled:
            return {"final_answer": "已取消", "final_sources": []}

        kb_evidence = self._build_kb_evidence(kb_chunks)
        full_steps = self._compress_step_results_for_context(step_results)
        user_prefs_str = self.memory_service.render_user_preferences_block()

        final_prompt = self.prompt_catalog.render(
            "synthesis_final_answer",
            question=question,
            step_results=full_steps,
            kb_evidence=kb_evidence + user_prefs_str,
        )

        final_answer = ""
        if stream_callback:
            cancel_event = getattr(self.agent_core, "_active_cancel_event", None)
            async for token in self.ask_stream_async_fn(
                final_prompt, temperature=self.agent_core.temperature, cancel_event=cancel_event
            ):
                final_answer += token
                stream_callback(token)
        else:
            final_answer = await self.ask_async_fn(final_prompt, temperature=self.agent_core.temperature)
            final_answer = final_answer.strip()

        final_answer = await self.agent_core._fix_terminology_async(final_answer, question)
        final_sources = self._filter_sources_by_citation(final_answer, list(sources or []))
        if persist_memory:
            await self.memory_service.apply_post_answer_effects_async(question, final_answer)
        return {"final_answer": final_answer, "final_sources": final_sources}
