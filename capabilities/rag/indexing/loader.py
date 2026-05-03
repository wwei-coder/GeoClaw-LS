import os

import fitz  # PyMuPDF
from docx import Document

from utils.logger import logger


def load_txt(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_pdf(path):
    text = ""
    with fitz.open(path) as doc:
        for page in doc:
            text += page.get_text() + "\n"
    return text


def load_docx(path):
    doc = Document(path)
    return "\n".join([p.text for p in doc.paragraphs])


def load_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".txt":
        return load_txt(path)
    if ext == ".pdf":
        return load_pdf(path)
    if ext == ".docx":
        return load_docx(path)
    raise ValueError("不支持的文件格式")


def load_documents_from_dir(dir_path, file_names=None):
    documents = []
    target_names = set(file_names or [])
    use_filter = len(target_names) > 0

    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
        return []

    for filename in os.listdir(dir_path):
        if filename.lower().endswith((".pdf", ".docx", ".txt")):
            if use_filter and filename not in target_names:
                continue
            full_path = os.path.join(dir_path, filename)
            try:
                text = load_file(full_path)
                documents.append({"name": filename, "path": full_path, "text": text})
                logger.info(f"✅ 已加载文档：{filename}")
            except Exception as e:
                logger.warning(f"❌ 加载失败：{filename}，原因：{e}")

    return documents
