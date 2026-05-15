from __future__ import annotations
from typing import Any
from capabilities.memory.service import ConversationMemoryService
from utils.ollama_client import (
    ask_ollama,
    ask_ollama_async,
    ask_ollama_stream,
    ask_ollama_stream_async,
)

from .synthesis import AnswerSynthesisService

def get_memory_service(agent_core: Any) -> ConversationMemoryService:
    service = getattr(agent_core, "_brain_synthesis_memory_service", None)
    if service is None or getattr(service, "agent_core", None) is not agent_core:
        service = ConversationMemoryService(agent_core)
        setattr(agent_core, "_brain_synthesis_memory_service", service)
    return service

def get_synthesis_service(agent_core: Any) -> AnswerSynthesisService:
    service = getattr(agent_core, "_brain_synthesis_service", None)
    memory_service = get_memory_service(agent_core)
    if service is None or getattr(service, "agent_core", None) is not agent_core:
        service = AnswerSynthesisService(
            agent_core=agent_core,
            memory_service=memory_service,
            ask_fn=ask_ollama,
            ask_async_fn=ask_ollama_async,
            ask_stream_fn=ask_ollama_stream,
            ask_stream_async_fn=ask_ollama_stream_async,
        )
        setattr(agent_core, "_brain_synthesis_service", service)
    else:
        service.memory_service = memory_service
    return service
