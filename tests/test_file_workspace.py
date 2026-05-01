import pytest

from core.file_workspace import FileWorkspace

def test_safe_name_and_extension_whitelist(tmp_path):
    ws = FileWorkspace(str(tmp_path / "workspace"))
    assert ws._safe_name("../a b?.csv") == "a_b_.csv"
    with pytest.raises(ValueError, match="仅支持上传"):
        ws.save_upload("bad.exe", b"payload")


def test_get_file_path_boundary(tmp_path):
    root = tmp_path / "workspace"
    ws = FileWorkspace(str(root))
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    ws._write_index(
        {
            "files": [
                {
                    "file_id": "file_x",
                    "original_name": "outside.txt",
                    "saved_name": "outside.txt",
                    "relative_path": "../outside.txt",
                    "size": 1,
                    "extension": ".txt",
                    "uploaded_at": "2026-01-01T00:00:00Z",
                }
            ],
            "artifacts": [],
        }
    )
    assert ws.get_file("file_x") is None
