import os
import re
import zipfile
from difflib import SequenceMatcher
from functools import lru_cache
from xml.etree import ElementTree as ET


NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}


def _cell_text(cell, shared_strings):
    t = cell.attrib.get("t")
    if t == "s":
        v = cell.find("x:v", NS)
        if v is None or v.text is None:
            return ""
        try:
            idx = int(v.text)
            return shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
        except ValueError:
            return ""
    if t == "inlineStr":
        texts = cell.findall(".//x:t", NS)
        return "".join([tt.text or "" for tt in texts]).strip()
    v = cell.find("x:v", NS)
    return (v.text or "").strip() if v is not None else ""


def _col_index(cell_ref):
    letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper()
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - 64)
    return max(0, idx - 1)


def _read_first_sheet_rows(xlsx_path):
    if not os.path.exists(xlsx_path):
        return []

    with zipfile.ZipFile(xlsx_path, "r") as zf:
        shared_strings = []
        if "xl/sharedStrings.xml" in zf.namelist():
            ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in ss_root.findall("x:si", NS):
                txt = "".join([(t.text or "") for t in si.findall(".//x:t", NS)]).strip()
                shared_strings.append(txt)

        workbook_root = ET.fromstring(zf.read("xl/workbook.xml"))
        first_sheet = workbook_root.find("x:sheets/x:sheet", NS)
        if first_sheet is None:
            return []

        rel_id = first_sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        rel_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        target = None
        for rel in rel_root.findall("r:Relationship", REL_NS):
            if rel.attrib.get("Id") == rel_id:
                target = rel.attrib.get("Target")
                break
        if not target:
            target = "worksheets/sheet1.xml"
        sheet_path = f"xl/{target}".replace("\\", "/")

        sheet_root = ET.fromstring(zf.read(sheet_path))
        rows = []
        for row in sheet_root.findall(".//x:sheetData/x:row", NS):
            values = []
            for cell in row.findall("x:c", NS):
                ref = cell.attrib.get("r", "")
                cidx = _col_index(ref) if ref else len(values)
                while len(values) <= cidx:
                    values.append("")
                values[cidx] = _cell_text(cell, shared_strings).strip()
            rows.append(values)
        return rows


def _tokenize(text):
    return [w for w in re.findall(r"[a-z0-9+/-]+", (text or "").lower()) if len(w) > 1]


def _score(question, query):
    q_norm = (question or "").strip().lower()
    u_norm = (query or "").strip().lower()
    if not q_norm or not u_norm:
        return 0.0

    ratio = SequenceMatcher(None, u_norm, q_norm).ratio()
    q_tokens = set(_tokenize(q_norm))
    u_tokens = set(_tokenize(u_norm))
    overlap = (len(q_tokens & u_tokens) / max(1, len(u_tokens)))

    phrase_bonus = 0.2 if (u_norm in q_norm or q_norm in u_norm) else 0.0
    return (0.55 * ratio) + (0.45 * overlap) + phrase_bonus


@lru_cache(maxsize=4)
def _load_kb_cached(xlsx_path, mtime):
    rows = _read_first_sheet_rows(xlsx_path)
    if not rows:
        return []

    header = [h.strip().lower() for h in rows[0]]
    q_idx, a_idx = 0, 1
    for i, col in enumerate(header):
        if "question" in col or col == "q":
            q_idx = i
        if "answer" in col or col == "a":
            a_idx = i

    qa = []
    for r in rows[1:]:
        q = r[q_idx].strip() if q_idx < len(r) else ""
        a = r[a_idx].strip() if a_idx < len(r) else ""
        if q and a:
            qa.append({"question": q, "answer": a})
    return qa


def load_knowledge_base(xlsx_path):
    if not os.path.exists(xlsx_path):
        return []
    return _load_kb_cached(xlsx_path, os.path.getmtime(xlsx_path))


def answer_from_excel(question, xlsx_path):
    kb = load_knowledge_base(xlsx_path)
    if not kb:
        return {
            "ok": False,
            "answer": "Knowledge file not found. Please upload the chatbot Excel knowledge base.",
            "confidence": 0.0,
            "source_question": None,
        }

    best = None
    best_score = 0.0
    for item in kb:
        s = _score(item["question"], question)
        if s > best_score:
            best = item
            best_score = s

    if best is None or best_score < 0.23:
        return {
            "ok": True,
            "answer": "I can answer only blood donation system questions from the Excel knowledge base. Please ask about donation, requests, blood groups, eligibility, or process.",
            "confidence": round(best_score, 3),
            "source_question": None,
        }

    return {
        "ok": True,
        "answer": best["answer"],
        "confidence": round(best_score, 3),
        "source_question": best["question"],
    }
