import json
import os


def generate_fingerprint(data_dir):
    fingerprint = {}
    if not os.path.exists(data_dir):
        return fingerprint

    for filename in os.listdir(data_dir):
        if filename.lower().endswith((".pdf", ".docx", ".txt")):
            path = os.path.join(data_dir, filename)
            stat = os.stat(path)
            fingerprint[filename] = {"mtime": stat.st_mtime, "size": stat.st_size}

    return fingerprint


def load_fingerprint(fp_path):
    if not os.path.exists(fp_path):
        return None

    with open(fp_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_fingerprint(fingerprint, fp_path):
    with open(fp_path, "w", encoding="utf-8") as f:
        json.dump(fingerprint, f, indent=2)


def diff_fingerprint(current_fp, saved_fp):
    current_fp = current_fp or {}
    saved_fp = saved_fp or {}

    current_docs = set(current_fp.keys())
    saved_docs = set(saved_fp.keys())

    added = sorted(current_docs - saved_docs)
    removed = sorted(saved_docs - current_docs)
    maybe_updated = current_docs & saved_docs
    updated = sorted([doc for doc in maybe_updated if current_fp.get(doc) != saved_fp.get(doc)])
    unchanged = sorted(list(maybe_updated - set(updated)))

    return {
        "added": added,
        "removed": removed,
        "updated": updated,
        "unchanged": unchanged,
        "changed": sorted(added + removed + updated),
    }
