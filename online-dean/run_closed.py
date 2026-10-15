#!/usr/bin/env python3
"""Пакетная обработка для сдачи: OCR (модуль 2) -> RAG-ответы (модуль 3) -> results.json.

  python3 run_closed.py --base dataset                       # открытый набор
  python3 run_closed.py --base <папка_с_закрытым_набором> --source image --profile fast
  python3 dataset/evaluate.py --reference dataset/reference_results.json --predictions results.json

В папке --base должны лежать documents.json и questions.json. Эталон (reference_results.json) здесь НЕ читается.
"""
import argparse
import json
import os
import traceback
from pathlib import Path

import ocr_engine
from dean_rag import DeanRAG
from doc_types import DOC_TYPES, NOT_FOUND
from pipeline import for_module3, process_document


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="dataset")
    ap.add_argument("--source", choices=["image", "pdf"], default="image")
    ap.add_argument("--profile", choices=list(ocr_engine.PROFILES), default="fast")
    ap.add_argument("--out", default="results.json")
    a = ap.parse_args()
    ocr_engine.OCR_OPTIONS = ocr_engine.PROFILES[a.profile]

    base = Path(a.base)
    documents = json.loads((base / "documents.json").read_text(encoding="utf-8"))
    questions = json.loads((base / "questions.json").read_text(encoding="utf-8"))
    by_doc = {}
    for q in questions:
        by_doc.setdefault(q["document_id"], []).append(q)

    rag = DeanRAG()
    cards, errors = [], []
    for item in documents:
        doc_id, doc_type = item["document_id"], item["document_type"]  # типы в манифесте известны заранее
        try:
            card = process_document(str(base / item[a.source]), doc_type=doc_type, document_id=doc_id, debug_dir="debug")
        except Exception:  # noqa: BLE001  один плохой файл не должен ронять весь прогон
            errors.append(doc_id + "\n" + traceback.format_exc())
            print("ОШИБКА", doc_id)
            card = {"document_id": doc_id, "document_type": doc_type,
                    "fields": {k: (False if c["kind"] == "mark" else NOT_FOUND)
                               for k, c in DOC_TYPES[doc_type]["fields"].items()}}
        cards.append(for_module3(card))
        print("OCR готово:", doc_id)

    results = [rag.process_document(c, by_doc.get(c["document_id"], [])) for c in cards]
    Path(a.out).write_text(json.dumps({"version": "1.0", "documents": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path("ocr_cards.json").write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
    if errors:
        Path("errors.txt").write_text("\n".join(errors), encoding="utf-8")
    print(f"Готово: {len(results)} документов -> {a.out}" + (f", ошибок: {len(errors)} (см. errors.txt)" if errors else ""))


if __name__ == "__main__":
    main()
