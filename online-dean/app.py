#!/usr/bin/env python3
"""Онлайн-деканат: единый сервер (модуль 2 - OCR и поля, модуль 3 - RAG по Положению, фронтенд).

Запуск:  python3 app.py   ->  http://localhost:5000
"""
import os
import tempfile
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import pipeline
from dean_rag import NOT_FOUND, DeanRAG

BASE = Path(__file__).resolve().parent
FRONT = BASE / "frontend"
ALLOWED = {".jpg", ".jpeg", ".png", ".pdf"}  # ТЗ: JPG, PNG или одностраничный PDF
STD_QUESTION = "Содержит ли документ все обязательные сведения по Положению?"

app = Flask(__name__, static_folder=str(FRONT / "static"), static_url_path="/static")
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024  # «до 15 МБ» как на странице
rag = DeanRAG()  # индекс Положения строится один раз при старте


# ----------------------------------------------------------------------------- вспомогательное
def bad(msg, code=400, hint=None):
    body = {"error": msg}
    if hint:
        body["hint"] = hint
    return jsonify(body), code


def card_view(card):
    """Карточка полей для UI: подпись, значение, статус ok/missing, пункт Положения."""
    dtype, fields = rag.normalize_card(card)
    rows = []
    for key, spec in rag.types[dtype]["fields"].items():
        v = fields[key]
        if spec["kind"] == "mark":
            rows.append({"key": key, "label": spec["label"], "value": "есть" if v else "нет",
                         "status": "ok" if v else "missing", "rule": spec["rule"]})
        else:
            rows.append({"key": key, "label": spec["label"], "value": v,
                         "status": "missing" if v == NOT_FOUND else "ok", "rule": spec["rule"]})
    return rows


def cited_rules(sources):
    ids = [s.split(":", 1)[1] for s in sources if s.startswith("rule:")]
    return [{"id": i, "text": rag.index.text(i)} for i in ids]


def respond(card, question, question_id, ocr_text=None):
    """Единый ответ для UI: карточка, проверка комплектности, ответ на вопрос, цитаты пунктов."""
    dtype, fields = rag.normalize_card(card)
    card = {"document_id": card.get("document_id", "web"), "document_type": dtype, "fields": fields}
    answer, trace = rag.answer_with_trace(card, question or STD_QUESTION, question_id)
    out = {"document_id": card["document_id"], "document_type": dtype,
           "document_title": rag.types[dtype]["title"], "fields": fields,
           "card": card_view(card), "validation": rag.validation_record(card),
           "answer": answer, "trace": trace, "cited_rules": cited_rules(answer["sources"]),
           "asked_question": bool(question)}
    if ocr_text is not None:
        out["ocr_text"] = ocr_text
    return out


def parse_card(body):
    if not isinstance(body, dict):
        return None, bad("Ожидался JSON-объект")
    dtype = body.get("document_type")
    if dtype not in rag.types:
        return None, bad(f"Неизвестный document_type: {dtype!r}. Доступны: {sorted(rag.types)}")
    if not isinstance(body.get("fields", {}), dict):
        return None, bad("fields должен быть объектом")
    return {"document_id": body.get("document_id", "web"), "document_type": dtype,
            "fields": body.get("fields", {})}, None


@app.errorhandler(413)
def too_big(_e):
    return bad("Файл больше 15 МБ", 413, hint="Сожмите фото или уменьшите разрешение.")


# ----------------------------------------------------------------------------- страницы
@app.route("/")
def index():
    return send_from_directory(FRONT, "index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok", "document_types": sorted(rag.types)})


# ----------------------------------------------------------------------------- основной сценарий
@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """multipart: file (jpg/png/pdf), [question], [document_type] (пусто или auto = определить по тексту)."""
    file = request.files.get("file")
    if file is None or not file.filename:
        return bad("Файл не выбран")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED:
        return bad("Нужен JPG, PNG или PDF")

    doc_type = (request.form.get("document_type") or "").strip()
    if doc_type in ("", "auto"):
        doc_type = None
    elif doc_type not in rag.types:
        return bad(f"Неизвестный тип документа: {doc_type!r}")

    question = (request.form.get("question") or "").strip()
    path = os.path.join(tempfile.gettempdir(), uuid.uuid4().hex + ext)
    file.save(path)
    try:
        doc, text = pipeline.process_document(path, doc_type=doc_type, document_id=file.filename, with_text=True)
        card = {"document_id": doc["document_id"], "document_type": doc["document_type"], "fields": doc["fields"]}
        return jsonify(respond(card, question, "web-Q1", ocr_text=text))
    except ValueError as e:  # нечитаемый снимок / тип не определён
        return bad(str(e), 422, hint="Сделайте новое чёткое фото или выберите тип документа вручную")
    except Exception as e:  # noqa: BLE001
        app.logger.exception("analyze failed")
        return bad("Не получилось распознать документ: " + str(e), 500)
    finally:
        if os.path.exists(path):
            os.remove(path)


@app.route("/api/answer", methods=["POST"])
def api_answer():
    """Новый вопрос по уже распознанной карточке (без повторного OCR)."""
    body = request.get_json(silent=True)
    card, err = parse_card(body)
    if err:
        return err
    question = (body.get("question") or "").strip()
    if not question:
        return bad("Пустой вопрос")
    return jsonify(respond(card, question, body.get("question_id", "web-Q1")))


@app.route("/api/check", methods=["POST"])
def api_check():
    """Проверка без вопроса: кнопка «Проверить документ» (п. 6.5 Положения)."""
    card, err = parse_card(request.get_json(silent=True))
    if err:
        return err
    return jsonify(respond(card, "", "web-check"))


@app.route("/api/schema/<dtype>")
def api_schema(dtype):
    if dtype not in rag.types:
        return bad(f"Неизвестный тип {dtype!r}", 404)
    return jsonify({"document_type": dtype, "title": rag.types[dtype]["title"],
                    "fields": [{"key": k, "label": f["label"], "kind": f["kind"], "rule": f["rule"]}
                               for k, f in rag.types[dtype]["fields"].items()]})


@app.route("/api/types")
def api_types():
    return jsonify([{"id": k, "title": v["title"]} for k, v in rag.types.items()])


@app.route("/api/rules")
@app.route("/api/rules/<cid>")
def api_rules(cid=None):
    if cid is None:
        return jsonify(rag.index.clauses)
    if cid not in rag.index.clauses:
        return bad(f"Пункт {cid} не найден", 404)
    return jsonify({"id": cid, "text": rag.index.text(cid)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
