from __future__ import annotations
from capabilities.base import CapabilityMetadata, CapabilityToolSpec
from .tool import KGRagTool

def get_capability() -> CapabilityMetadata:
    return CapabilityMetadata(
        name="kg_rag",
        description="Knowledge-graph enhanced RAG capability scaffold (disabled by default).",
        enabled=False,
        tools={
            "KG_RAG": CapabilityToolSpec(
                tool_name="KG_RAG",
                description="KG-RAG hybrid retrieval tool (stub).",
                tool_factory=KGRagTool,
                enabled=True,
            )
        },
    )
