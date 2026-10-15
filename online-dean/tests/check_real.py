#!/usr/bin/env python3
"""Проверка с НАСТОЯЩИМ OCR через сайт (как студент): python tests/check_real.py [image|pdf] [fast|accurate]

Каждый из 30 открытых документов отправляется на /api/analyze с типом «авто». Сравнивается с эталоном:
тип документа, поля, статус и пропуски комплектности. Отчёт печатается и сохраняется в check_report.txt.
"""
import io, json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
source = sys.argv[1] if len(sys.argv) > 1 else "image"
profile = sys.argv[2] if len(sys.argv) > 2 else "fast"

import ocr_engine
ocr_engine.OCR_OPTIONS = ocr_engine.PROFILES[profile]
import app as web

norm = lambda v: " ".join(str(v).casefold().replace("ё", "е").split())
client = web.app.test_client()
docs = json.loads((ROOT / "dataset/documents.json").read_text(encoding="utf-8"))
ref = {d["document_id"]: d for d in json.loads((ROOT / "dataset/reference_results.json").read_text(encoding="utf-8"))["documents"]}
report, t_ok, v_ok, f_ok, f_all, times, cards = [], 0, 0, 0, 0, [], {}

for item in docs:
    did = item["document_id"]; path = ROOT / "dataset" / item[source]; r = ref[did]
    t0 = time.time()
    resp = client.post("/api/analyze", data={"file": (io.BytesIO(path.read_bytes()), did + path.suffix), "document_type": "auto"},
                       content_type="multipart/form-data")
    times.append(time.time() - t0)
    if resp.status_code != 200:
        report.append(f"{did}  ОШИБКА {resp.status_code}: {resp.get_json().get('error')}"); f_all += len(r["fields"]); continue
    j = resp.get_json(); cards[did] = j
    bad = []
    if j["document_type"] == item["document_type"]: t_ok += 1
    else: bad.append(f"тип: ждали {item['document_type']}, получили {j['document_type']}")
    for k, exp in r["fields"].items():
        f_all += 1
        got = j["fields"].get(k)
        if (isinstance(exp, bool) and got is exp) or (not isinstance(exp, bool) and norm(got) == norm(exp)): f_ok += 1
        else: bad.append(f"поле {k}: ждали {exp!r}, получили {got!r}")
    v, rv = j["validation"], r["validation"]
    if v["status"] == rv["status"] and sorted(v["missing_fields"]) == sorted(rv["missing_fields"]): v_ok += 1
    else: bad.append(f"комплектность: ждали {rv['status']} {rv['missing_fields']}, получили {v['status']} {v['missing_fields']}")
    report.append(f"{did}  {'OK' if not bad else 'РАСХОЖДЕНИЯ'}  ({times[-1]:.1f} с)" + "".join("\n      - " + b for b in bad))

# вопрос без ответа по реальной карточке
first = next(iter(cards.values()), None)
if first:
    a = client.post("/api/answer", json={"document_type": first["document_type"], "fields": first["fields"],
                                         "question": "Какой размер стипендии положен студенту?"}).get_json()["answer"]
    report.append(f"\nВопрос без ответа: answerable={a['answerable']} (ждали False), sources={a['sources']} (ждали []) -> «{a['answer']}»")

n = len(docs)
report += ["", f"ИТОГО ({source}, профиль {profile}):",
           f"  тип определён верно:       {t_ok}/{n}",
           f"  поля верно:                {f_ok}/{f_all}  ({f_ok / max(f_all, 1):.1%})",
           f"  комплектность верно:       {v_ok}/{n}",
           f"  среднее время на документ: {sum(times) / max(len(times), 1):.1f} с"]
text = "\n".join(report)
print(text); (ROOT / "check_report.txt").write_text(text, encoding="utf-8")
