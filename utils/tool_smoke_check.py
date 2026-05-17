from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.registry import execute_tool, get_tool_registry

class _WorkspaceNoFile:
    uploads_dir = Path("workspace/uploads").resolve()

    def resolve_file_from_query(self, query: str, fallback_file_id=None):  # noqa: D401
        _ = (query, fallback_file_id)
        return None

class _WorkspaceUnsafePath:
    uploads_dir = Path("workspace/uploads").resolve()

    def resolve_file_from_query(self, query: str, fallback_file_id=None):  # noqa: D401
        _ = (query, fallback_file_id)
        return {
            "file_id": "file_x",
            "original_name": "unsafe.csv",
            "extension": ".csv",
            "size": 1,
            "abs_path": str(Path("d:/outside/unsafe.csv").resolve()),
        }

class _AgentStub:
    def __init__(self, workspace=None):
        self.file_workspace = workspace
        self.active_file_id = None

def _assert(condition: bool, msg: str, failures: list[str]) -> None:
    if condition:
        print(f"[PASS] {msg}")
    else:
        print(f"[FAIL] {msg}")
        failures.append(msg)

def main() -> int:
    failures: list[str] = []
    registry = get_tool_registry()

    unknown = execute_tool("UNKNOWN_TOOL", "x", _AgentStub(), registry=registry)
    _assert((not unknown.success) and "未知工具" in str(unknown.error or ""), "未知工具处理", failures)

    no_file = execute_tool("DATA_PROFILE", "请分析这个文件", _AgentStub(_WorkspaceNoFile()), registry=registry)
    _assert((not no_file.success) and no_file.error == "file_not_found", "DATA_PROFILE 无 file_id 错误返回", failures)

    unsafe = execute_tool("FILE_INSPECTOR", "file_id:file_x", _AgentStub(_WorkspaceUnsafePath()), registry=registry)
    _assert((not unsafe.success) and unsafe.error == "invalid_file_path", "FILE_INSPECTOR 路径安全", failures)

    if failures:
        print(f"\n共失败 {len(failures)} 项")
        return 1
    print("\n全部检查通过")
    return 0

if __name__ == "__main__":
    sys.exit(main())
