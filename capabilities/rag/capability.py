from __future__ import annotations
from capabilities.base import CapabilityMetadata, CapabilityToolSpec
from tools.rag_tool import RagTool

def get_capability() -> CapabilityMetadata:
    return CapabilityMetadata(
        name="rag",
        description="知识库检索能力（当前默认启用）",
        enabled=True,
        tools={
            "RAG": CapabilityToolSpec(
                tool_name="RAG",
                description="从知识库检索相关资料",
                tool_factory=RagTool,
                enabled=True,
            )
        },
    )
