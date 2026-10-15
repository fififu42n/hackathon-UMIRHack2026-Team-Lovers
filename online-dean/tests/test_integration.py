#!/usr/bin/env python3
"""Интеграционный тест всей цепочки БЕЗ реального OCR (easyocr тяжёлый): python3 tests/test_integration.py

OCR подменяется текстом, собранным из эталона в «живом» оформлении (даты в разных форматах).
Всё остальное настоящее: поиск полей, определение подписи/печати по пикселям PNG, RAG, Flask, evaluate.py.
"""
import io, json, os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)

import pipeline
from doc_types import DOC_TYPES, NOT_FOUND

REF = json.loads((ROOT / "dataset/reference_results.json").read_text(encoding="utf-8"))["documents"]
REF = {d["document_id"]: d for d in REF}
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def fake_text(doc_id, i):
    ref = REF[doc_id]; cfg = DOC_TYPES[ref["document_type"]]["fields"]
    lines = ["Справка / заявление / документ"]
    for key, c in cfg.items():
        if c["kind"] == "mark":
            continue
        v = ref["fields"][key]
        if v == NOT_FOUND:
            continue
        if c["kind"] == "date":
            y, m, d = v.split("-")
            v = f"{d}.{m}.{y}" if i % 2 else f"{int(d)} {MONTHS[int(m)-1]} {y} года"
        lines.append(f"{c['labels'][0]}: {v}")
    return "\n".join(lines) + "\n" + "Текст для длины. " * 5


def install_fake_ocr():
    counter = {"i": 0}
    def recognize(path):
        counter["i"] += 1
        return fake_text(Path(path).stem if Path(path).stem in REF else os.environ["FAKE_DOC_ID"], counter["i"])
    pipeline.recognize = recognize


fails = 0
def check(name, cond, info=""):
    global fails
    if not cond:
        fails += 1; print("FAIL", name, info)

# --- 1. пакетный режим: run_closed.py -> evaluate.py
install_fake_ocr()
import run_closed
TMP = os.path.join(tempfile.mkdtemp(), "results_it.json")
sys.argv = ["run_closed.py", "--base", "dataset", "--out", TMP]
run_closed.main()
out = subprocess.run([sys.executable, "dataset/evaluate.py", "--reference", "dataset/reference_results.json",
                      "--predictions", TMP], capture_output=True, text=True)
print(out.stdout[-900:], out.stderr[-300:])
check("evaluate ok", out.returncode == 0, out.stderr)

# --- 2. веб: загрузка файла -> карточка + ответ
import app as web
client = web.app.test_client()
docs = json.loads((ROOT / "dataset/documents.json").read_text(encoding="utf-8"))
for item in docs[:3] + docs[10:12] + docs[20:22]:
    did = item["document_id"]; os.environ["FAKE_DOC_ID"] = did
    png = (ROOT / "dataset" / item["image"]).read_bytes()
    for q in ["", "Укажи значение поля «Номер справки»", "Кто принимает окончательное решение о принятии документа?", "Какая погода в деканате?"]:
        r = client.post("/api/analyze", data={"file": (io.BytesIO(png), did + ".png"), "document_type": "auto", "question": q},
                        content_type="multipart/form-data")
        check(f"analyze {did} q={q[:15]!r}", r.status_code == 200, r.get_data(as_text=True)[:200])
        if r.status_code == 200:
            j = r.get_json()
            check(f"type {did}", j["document_type"] == item["document_type"], j["document_type"])
            check(f"status {did}", j["validation"]["status"] == REF[did]["validation"]["status"], j["validation"])
            check(f"answer fmt {did}", set(j["answer"]) == {"question_id", "answerable", "value", "answer", "sources"})
check("weather unanswerable", client.post("/api/answer", json={"document_type": "study_certificate", "fields": {}, "question": "Какая погода?"}).get_json()["answer"]["answerable"] is False)

# --- 3. плохой снимок / не тот формат / нет файла
pipeline.recognize = lambda p: "мусор"
r = client.post("/api/analyze", data={"file": (io.BytesIO(png), "x.png")}, content_type="multipart/form-data")
check("bad photo 422", r.status_code == 422 and "error" in r.get_json(), r.get_data(as_text=True))
r = client.post("/api/analyze", data={"file": (io.BytesIO(b"x"), "x.exe")}, content_type="multipart/form-data")
check("bad ext 400", r.status_code == 400)
check("no file 400", client.post("/api/analyze", data={}, content_type="multipart/form-data").status_code == 400)
check("index page", client.get("/").status_code == 200 and b"app.js" in client.get("/").data)
check("static js", client.get("/static/app.js").status_code == 200)
check("health", client.get("/health").get_json()["status"] == "ok")

print("OK, все интеграционные тесты пройдены" if not fails else f"ПРОВАЛЕНО: {fails}")
sys.exit(1 if fails else 0)
