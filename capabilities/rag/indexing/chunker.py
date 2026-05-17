import os
import re
import uuid
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config_runtime import (
    CHUNK_CHILD_DEFAULT_SIZE,
    CHUNK_CHILD_NUMERIC_SIZE,
    CHUNK_CHILD_NUMERIC_THRESHOLD,
    CHUNK_DYNAMIC_BASE_RATIO,
    CHUNK_DYNAMIC_DIGIT_BONUS,
    CHUNK_DYNAMIC_DIGIT_RATIO_THRESHOLD,
    CHUNK_DYNAMIC_MAX_RATIO,
    CHUNK_DYNAMIC_MIN_OVERLAP,
    CHUNK_DYNAMIC_SHORT_LINE_BONUS,
    CHUNK_DYNAMIC_TABLE_BONUS,
    CHUNK_PARENT_DEFAULT_SIZE,
    CHUNK_PARENT_LARGE_SIZE,
    CHUNK_PARENT_LARGE_THRESHOLD,
)

HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+.+|第[一二三四五六七八九十百零\d]+[章节部分篇]\s*.*|[一二三四五六七八九十]+[、.．]\s*.+|\d+(?:\.\d+){0,3}\s+.+)\s*$"
)
PAGE_MARKER_RE = re.compile(r"\[页码:\s*(\d+)\]")

def _detect_doc_type(doc_name: str) -> str:
    ext = os.path.splitext((doc_name or "").lower())[1]
    if ext == ".pdf":
        return "report"
    if ext == ".docx":
        return "paper"
    if ext in {".csv", ".xlsx", ".xls"}:
        return "data"
    if ext in {".md", ".txt"}:
        return "knowledge"
    return "knowledge"

def _extract_year(text: str, doc_name: str):
    text = text or ""
    doc_name = doc_name or ""
    m = re.search(r"(19\d{2}|20\d{2})", doc_name)
    if m:
        return int(m.group(1))
    m = re.search(r"(19\d{2}|20\d{2})", text[:2000])
    if m:
        return int(m.group(1))
    return None

def _dynamic_overlap(chunk_size: int, text: str) -> int:
    text = text or ""
    base = max(CHUNK_DYNAMIC_MIN_OVERLAP, int(chunk_size * CHUNK_DYNAMIC_BASE_RATIO))
    digit_ratio = len(re.findall(r"\d", text[:2000])) / max(1, len(text[:2000]))
    line_count = max(1, text.count("\n"))
    short_line_bonus = CHUNK_DYNAMIC_SHORT_LINE_BONUS if (len(text) / line_count) < 25 else 0
    table_bonus = CHUNK_DYNAMIC_TABLE_BONUS if ("|" in text or "\t" in text) else 0
    digit_bonus = CHUNK_DYNAMIC_DIGIT_BONUS if digit_ratio > CHUNK_DYNAMIC_DIGIT_RATIO_THRESHOLD else 0
    overlap = base + short_line_bonus + table_bonus + digit_bonus
    return max(CHUNK_DYNAMIC_MIN_OVERLAP, min(int(chunk_size * CHUNK_DYNAMIC_MAX_RATIO), overlap))

def _split_by_sections(text: str):
    text = (text or "").strip()
    if not text:
        return []
    heading_re = re.compile(r"(?m)" + HEADING_RE.pattern)
    matches = list(heading_re.finditer(text))
    if not matches:
        paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        return paras if paras else [text]
    sections = []
    first_start = matches[0].start()
    if first_start > 0:
        preface = text[:first_start].strip()
        if preface:
            sections.append(preface)
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        if block:
            sections.append(block)
    return sections if sections else [text]

def _section_title(section: str) -> str:
    for line in str(section or "").splitlines():
        cleaned = line.strip()
        if not cleaned or PAGE_MARKER_RE.fullmatch(cleaned):
            continue
        if HEADING_RE.match(cleaned):
            return cleaned[:120]
        if len(cleaned) <= 60 and not cleaned.endswith(("。", "；", "，", ",")):
            return cleaned[:120]
        break
    return ""

def _infer_page_num(*texts: str):
    for text in texts:
        match = PAGE_MARKER_RE.search(str(text or ""))
        if match:
            try:
                return int(match.group(1))
            except Exception:
                return None
    return None

def _clean_page_markers(text: str) -> str:
    return PAGE_MARKER_RE.sub("", str(text or "")).strip()

def split_text(text, chunk_size=500, overlap=100):
    sections = _split_by_sections(text)
    all_chunks = []
    for sec in sections:
        real_overlap = _dynamic_overlap(chunk_size, sec) if overlap is None else overlap
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=real_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " ", ""],
        )
        all_chunks.extend(splitter.split_text(sec))
    return all_chunks

def build_knowledge_chunks(documents):
    all_chunks = []
    for doc in documents:
        doc_name = doc.get("name", "unknown")
        doc_text = doc.get("text", "") or ""
        doc_type = _detect_doc_type(doc_name)
        doc_year = _extract_year(doc_text, doc_name)
        sections = _split_by_sections(doc_text)
        if not sections:
            continue
        last_seen_page = None
        for s_idx, section in enumerate(sections):
            marker_page = _infer_page_num(section)
            if marker_page:
                last_seen_page = marker_page
            section_title = _section_title(section)
            section_page = marker_page or last_seen_page
            if not _clean_page_markers(section):
                continue
            parent_chunk_size = (
                CHUNK_PARENT_LARGE_SIZE
                if len(section) > CHUNK_PARENT_LARGE_THRESHOLD
                else CHUNK_PARENT_DEFAULT_SIZE
            )
            parent_overlap = _dynamic_overlap(parent_chunk_size, section)
            parent_splitter = RecursiveCharacterTextSplitter(
                chunk_size=parent_chunk_size,
                chunk_overlap=parent_overlap,
                separators=["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " ", ""],
            )
            parent_chunks = parent_splitter.split_text(section)
            for p_idx, parent_content in enumerate(parent_chunks):
                parent_page = _infer_page_num(parent_content, section) or section_page or 0
                clean_parent_content = _clean_page_markers(parent_content)
                parent_id = f"{doc_name}::parent_{s_idx}_{p_idx}::{uuid.uuid4().hex[:6]}"
                child_chunk_size = (
                    CHUNK_CHILD_NUMERIC_SIZE
                    if len(re.findall(r"\d", parent_content)) > CHUNK_CHILD_NUMERIC_THRESHOLD
                    else CHUNK_CHILD_DEFAULT_SIZE
                )
                child_overlap = _dynamic_overlap(child_chunk_size, parent_content)
                child_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=child_chunk_size,
                    chunk_overlap=child_overlap,
                    separators=["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " ", ""],
                )
                child_chunks = child_splitter.split_text(parent_content)
                for c_idx, child_content in enumerate(child_chunks):
                    page_num = _infer_page_num(child_content, parent_content, section) or parent_page or 0
                    clean_child_content = _clean_page_markers(child_content)
                    if not clean_child_content:
                        continue
                    chunk_id = f"{doc_name}::child_{s_idx}_{p_idx}_{c_idx}::{uuid.uuid4().hex[:6]}"
                    item = {
                        "id": chunk_id,
                        "doc_name": doc_name,
                        "content": clean_child_content,
                        "parent_content": clean_parent_content,
                        "parent_id": parent_id,
                        "section_idx": s_idx,
                        "section_title": section_title,
                        "page_num": page_num,
                        "parent_idx": p_idx,
                        "child_idx": c_idx,
                        "type": doc_type,
                        "active": True,
                    }
                    if doc_year:
                        item["year"] = doc_year
                    all_chunks.append(item)
    return all_chunks
