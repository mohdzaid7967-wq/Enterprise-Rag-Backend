import os
import re
from typing import List, Dict, Any
from pypdf import PdfReader
from docx import Document as DocxDocument
import tiktoken

tokenizer = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(tokenizer.encode(text))

def clean_text(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def split_into_sentences(text: str) -> List[str]:
    # Regex split that preserves sentence terminators without cutting mid-sentence
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]

def is_heading(line: str) -> bool:
    line = line.strip()
    if not line:
        return False
    # Markdown heading, numbered section, or short capitalized header
    if line.startswith("#"):
        return True
    if re.match(r"^\d+(\.\d+)*\s+[A-Z]", line):
        return True
    if len(line) < 60 and line.isupper():
        return True
    return False

def extract_text_from_file(file_path: str, file_type: str) -> List[Dict[str, Any]]:
    pages_data = []

    if file_type == "pdf":
        reader = PdfReader(file_path)
        for idx, page in enumerate(reader.pages):
            raw = page.extract_text() or ""
            cleaned = clean_text(raw)
            if cleaned:
                pages_data.append({"text": cleaned, "page_number": idx + 1})

    elif file_type == "docx":
        doc = DocxDocument(file_path)
        full_text = "\n\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        cleaned = clean_text(full_text)
        if cleaned:
            pages_data.append({"text": cleaned, "page_number": 1})

    elif file_type in ("txt", "md"):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
        cleaned = clean_text(raw)
        if cleaned:
            pages_data.append({"text": cleaned, "page_number": 1})

    return pages_data

def create_chunks(
    pages_data: List[Dict[str, Any]],
    target_tokens: int = 500,
    overlap_tokens: int = 80
) -> List[Dict[str, Any]]:
    final_chunks = []
    chunk_index = 0

    for page in pages_data:
        lines = page["text"].split("\n")
        current_section = f"Page {page['page_number']}"
        current_sentences = []
        current_tokens = 0

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Heading detected: flush previous chunk so unrelated sections do not mix
            if is_heading(line_str):
                if current_sentences:
                    chunk_text = " ".join(current_sentences).strip()
                    final_chunks.append({
                        "chunk_index": chunk_index,
                        "content": f"[{current_section}]\n{chunk_text}",
                        "page_number": page["page_number"],
                        "section": current_section
                    })
                    chunk_index += 1
                    current_sentences = []
                    current_tokens = 0
                current_section = line_str.lstrip("#").strip()
                continue

            # Split paragraph into full sentences to avoid cutting mid-sentence
            sentences = split_into_sentences(line_str)
            for sentence in sentences:
                s_tokens = count_tokens(sentence)

                if current_tokens + s_tokens <= target_tokens:
                    current_sentences.append(sentence)
                    current_tokens += s_tokens
                else:
                    if current_sentences:
                        chunk_text = " ".join(current_sentences).strip()
                        final_chunks.append({
                            "chunk_index": chunk_index,
                            "content": f"[{current_section}]\n{chunk_text}",
                            "page_number": page["page_number"],
                            "section": current_section
                        })
                        chunk_index += 1

                    # Keep a sentence overlap buffer when possible
                    overlap_buffer = []
                    overlap_count = 0
                    for prev_s in reversed(current_sentences):
                        t_count = count_tokens(prev_s)
                        if overlap_count + t_count <= overlap_tokens:
                            overlap_buffer.insert(0, prev_s)
                            overlap_count += t_count
                        else:
                            break

                    current_sentences = overlap_buffer + [sentence]
                    current_tokens = sum(count_tokens(s) for s in current_sentences)

        # Flush any remaining text on the page
        if current_sentences:
            chunk_text = " ".join(current_sentences).strip()
            final_chunks.append({
                "chunk_index": chunk_index,
                "content": f"[{current_section}]\n{chunk_text}",
                "page_number": page["page_number"],
                "section": current_section
            })
            chunk_index += 1

    return final_chunks