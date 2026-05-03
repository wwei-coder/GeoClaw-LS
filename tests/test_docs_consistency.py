from __future__ import annotations
from pathlib import Path

DELETED_COMPAT_LAYER_DECLARATION = "兼容层目录 `rag/`、`knowledge/`、`memory/` 已删除"
LEGACY_PATH_REMOVED_DECLARATION = "旧导入路径已下线"
LEGACY_PATH_RETAINED_DECLARATION = "旧导入路径仍保留"

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]

def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def _compat_layer_dirs(root: Path) -> list[Path]:
    return [root / "rag", root / "knowledge", root / "memory"]

def test_migration_status_fact_source_exists():
    root = _repo_root()
    status_doc = root / "docs" / "migration_status.md"
    assert status_doc.exists()
    text = _read_text(status_doc)
    assert "事实源" in text
    assert DELETED_COMPAT_LAYER_DECLARATION in text
    assert LEGACY_PATH_REMOVED_DECLARATION in text

def test_deleted_compat_layer_declaration_matches_filesystem():
    root = _repo_root()
    docs = [
        root / "AGENTS.md",
        root / "docs" / "architecture_target.md",
        root / "docs" / "migration_status.md",
    ]
    compat_dirs = _compat_layer_dirs(root)

    for doc in docs:
        text = _read_text(doc)
        if DELETED_COMPAT_LAYER_DECLARATION in text:
            assert all(not p.exists() for p in compat_dirs), f"{doc} 声明已删除，但目录仍存在"


def test_legacy_path_retained_declaration_matches_filesystem():
    root = _repo_root()
    docs = [
        root / "AGENTS.md",
        root / "docs" / "architecture_target.md",
        root / "docs" / "migration_status.md",
    ]
    compat_dirs = _compat_layer_dirs(root)

    for doc in docs:
        text = _read_text(doc)
        if LEGACY_PATH_RETAINED_DECLARATION in text:
            assert all(p.exists() for p in compat_dirs), f"{doc} 声明仍保留，但目录不存在"


def test_main_docs_agree_legacy_imports_removed():
    root = _repo_root()
    docs = [
        root / "AGENTS.md",
        root / "docs" / "architecture_target.md",
        root / "docs" / "migration_status.md",
    ]

    for doc in docs:
        text = _read_text(doc)
        assert LEGACY_PATH_REMOVED_DECLARATION in text, f"{doc} 未明确声明旧导入路径已下线"
