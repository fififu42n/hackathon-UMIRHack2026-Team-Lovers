#!/usr/bin/env python3
"""Модуль 3 «Онлайн-деканат»: проверка комплектности и ответы на вопросы.

Вход : карточка документа от OCR-модуля (document_type + fields) и вопрос на русском.
Выход: запись answer в формате results.json (question_id, answerable, value, answer, sources)
       и validation (status, missing_fields, sources).

Только стандартная библиотека. Нейросети и внешние API не используются:
  1. маршрутизация вопроса (комплектность / решение / поле / вопрос по Положению);
  2. поиск по индексу пунктов rules.md (лексический, TF-IDF по основам слов);
  3. шаблонные ответы со ссылками на field:<ключ> и rule:<N.M>.
"""
import argparse
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOT_FOUND = "не найдено"
NO_INFO = "В документе и в Положении нет информации для ответа на этот вопрос. Обратитесь в деканат."
DECISION_VALUE = "сотрудник деканата"

MONTHS = {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6, "июля": 7,
          "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12}


# ----------------------------------------------------------------------------- утилиты
def norm_text(s):
    s = unicodedata.normalize("NFC", str(s)).casefold().replace("ё", "е")
    for ch in "«»“”„":
        s = s.replace(ch, '"')
    return re.sub(r"\s+", " ", s).strip()


def to_iso_date(value):
    """'01.09.2026', '1 сентября 2026 года', '2026-09-01' -> '2026-09-01'. Иначе значение как есть."""
    s = norm_text(value)
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return s
    m = re.search(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", s)
    if m:
        d, mo, y = map(int, m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}"
    m = re.search(r"\b(\d{1,2})\s+([а-я]+)\s+(\d{4})", s)
    if m and m.group(2) in MONTHS:
        return f"{int(m.group(3)):04d}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"
    return str(value).strip()


def is_missing_text(v):
    return v is None or not str(v).strip() or norm_text(v) in (NOT_FOUND, "не найден", "none", "null")


# ----------------------------------------------------------------------------- индекс Положения
STOP = set("""а и в во не на с со к по о об от до из за для или как что это то же ли бы так при про
какой какая какое какие каков какова каковы какую каким какого какому какой где когда кто чей
есть быть был была были будет можно нужно надо ли ещё еще мой моя мои меня мне вас вам наш
укажи скажи подскажите расскажи пожалуйста значение""".split())
GENERIC_STEMS = {"докум", "деканат", "студе", "полож", "серви", "справ", "заявл"}  # шумят в каждом пункте


def stem(tok):
    return tok[:5] if len(tok) > 5 else tok


def content_stems(text):
    toks = re.findall(r"[а-яa-z0-9]+", norm_text(text))
    return [stem(t) for t in toks if len(t) > 2 and t not in STOP]


class RulesIndex:
    """Разбор rules.md на пронумерованные пункты + поиск по ним."""

    def __init__(self, path):
        self.clauses = {}   # "3.1" -> текст
        self.section = {}   # "3.1" -> заголовок раздела
        sec = ""
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                sec = line[3:].strip()
                continue
            m = re.match(r"^(\d+\.\d+)\.\s+(.*\S)\s*$", line)
            if m:
                self.clauses[m.group(1)] = m.group(2)
                self.section[m.group(1)] = sec
        # раздел 6 — шаблоны формулировок, в поиск не включаем
        self._docs = {cid: set(content_stems(t)) for cid, t in self.clauses.items() if not cid.startswith("6.")}
        n = len(self._docs)
        df = {}
        for st in self._docs.values():
            for s in st:
                df[s] = df.get(s, 0) + 1
        self._idf = {s: math.log(1 + n / c) for s, c in df.items()}

    def text(self, cid):
        return self.clauses[cid]

    def search(self, question, min_score=0.6):
        """Возвращает (clause_id, score) или None. Порог намеренно высокий: лучше «нет информации»,
        чем выдуманный ответ (требование п. 2.4 Положения)."""
        q = list(dict.fromkeys(content_stems(question)))
        if not q:
            return None
        w = lambda s: (0.25 if s in GENERIC_STEMS else 1.0) * self._idf.get(s, 1.5)
        total = sum(w(s) for s in q)
        specific = [s for s in q if s not in GENERIC_STEMS]
        best = None
        for cid, st in self._docs.items():
            hit = [s for s in q if s in st]
            hit_spec = [s for s in hit if s not in GENERIC_STEMS]
            score = sum(w(s) for s in hit) / total
            enough = len(hit_spec) >= 2 or (len(specific) == 1 and len(hit_spec) == 1)
            if enough and score >= min_score and (best is None or score > best[1]):
                best = (cid, score)
        return best


# ----------------------------------------------------------------------------- основной класс
class DeanRAG:
    def __init__(self, rules_path=HERE / "rules.md", config_path=HERE / "doc_types.json"):
        self.index = RulesIndex(rules_path)
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
        self.not_established = set(cfg.pop("_not_established_rules", []))
        cfg.pop("_comment", None)
        self.types = cfg

    # ---- нормализация карточки от OCR
    def normalize_card(self, card):
        dtype = card["document_type"]
        spec = self.types[dtype]["fields"]
        raw = card.get("fields", {}) or {}
        fields = {}
        for key, f in spec.items():
            v = raw.get(key)
            if f["kind"] == "mark":
                fields[key] = v is True or (isinstance(v, str) and norm_text(v) in ("true", "да", "есть"))
            elif is_missing_text(v):
                fields[key] = NOT_FOUND
            elif f["kind"] == "date":
                fields[key] = to_iso_date(v)
            elif key == "course":
                m = re.match(r"\s*(\d+)", str(v))
                fields[key] = m.group(1) if m else str(v).strip()
            else:
                fields[key] = str(v).strip()
        return dtype, fields

    # ---- предварительная проверка (пп. 3.4, 4.5, 5.4, 6.1, 6.2)
    def validate(self, card):
        dtype, fields = self.normalize_card(card)
        spec = self.types[dtype]["fields"]
        missing = [k for k, f in spec.items()
                   if (f["kind"] == "mark" and fields[k] is not True)
                   or (f["kind"] != "mark" and fields[k] == NOT_FOUND)]
        rule_ids = {spec[k]["rule"] for k in (missing or spec)}
        return {"status": "missing_fields" if missing else "document_ok",
                "missing_fields": missing,
                "sources": sorted(rule_ids, key=lambda r: tuple(map(int, r.split("."))))}  # без префикса, см. ниже

    def _rule_refs(self, ids):
        return [f"rule:{i}" for i in ids]

    def validation_record(self, card):
        v = self.validate(card)
        return {"status": v["status"], "missing_fields": v["missing_fields"], "sources": self._rule_refs(v["sources"])}

    # ---- маршрутизация вопроса
    def _find_field(self, dtype, question):
        """(key, kind_of_match, foreign_label) — поле по вопросу. Сначала подпись в «», затем паттерны."""
        q = norm_text(question)
        quoted = re.findall(r'"([^"]+)"', q)
        own = self.types[dtype]["fields"]
        for qt in quoted:
            for k, f in own.items():
                if norm_text(f["label"]) == qt:
                    return k, None
        best = None  # самый длинный совпавший паттерн
        for k, f in own.items():
            for p in f["patterns"]:
                m = re.search(p, q)
                weight = len(m.group(0)) + (100 if f["kind"] == "mark" else 0) if m else 0  # «подпись/печать руководителя» -> отметка, не ФИО
                if m and (best is None or weight > best[0]):
                    best = (weight, k)
        if best:
            return best[1], None
        # поле из другого типа документа
        for t, spec in self.types.items():
            if t == dtype:
                continue
            for k, f in spec["fields"].items():
                if any(norm_text(f["label"]) == qt for qt in quoted) or any(re.search(p, q) for p in f["patterns"]):
                    return None, f["label"]
        if quoted:  # явно названо поле, которого нет ни в одном типе
            return None, quoted[0]
        return None, None

    RE_DECISION = re.compile(r"\bкто\b.*(принима|решени|решает|утвержда|одобря)|"
                             r"(принят|одобрен|утвержден)\w*\s+ли\b|\bкто\b.*(окончательн)")
    RE_COMPLETE = re.compile(r"обязательн|все ли|всё ли|полност|достаточн|хватает|хватит|не хватает|чего не|комплект|подойд|годится|"
                             r"в порядке|содержит ли|подходит ли|корректн|правильно ли заполн|что (нужно|надо) (исправ|добав|дозапол)|"
                             r"проверь|проверка|можно ли (подавать|сдавать|отправ)")

    def answer(self, card, question, question_id=None):
        return self.answer_with_trace(card, question, question_id)[0]

    def answer_with_trace(self, card, question, question_id=None):
        """Возвращает (answer_record, trace). trace нужен интерфейсу: какое поле/пункт использован."""
        ans, trace = self._route(card, question)
        ans["question_id"] = question_id
        return ans, trace

    def _route(self, card, question):
        dtype, fields = self.normalize_card(card)
        spec = self.types[dtype]["fields"]
        q = norm_text(question)
        val = self.validate(card)

        def rec(answerable, value, text, sources):
            return {"question_id": None, "answerable": answerable, "value": value,
                    "answer": text, "sources": sources}

        quoted_field, _ = self._find_field(dtype, question) if re.search(r'"[^"]+"', q) else (None, None)

        # 1. кто принимает решение (п. 1.3)
        if self.RE_DECISION.search(q) and not quoted_field:
            text = ("Окончательное решение о принятии документа принимает сотрудник деканата, пункт 1.3 Положения. "
                    "Сервис выполняет только предварительную проверку и не сообщает, что документ принят.")
            return rec(True, DECISION_VALUE, text, ["rule:1.3"]), {"route": "decision", "rules": ["1.3"]}

        # 2. комплектность
        if not quoted_field and self.RE_COMPLETE.search(q):
            return self._completeness(dtype, fields, val), {"route": "completeness", "rules": val["sources"],
                                                           "missing": val["missing_fields"]}

        # 3. значение поля
        key, foreign = self._find_field(dtype, question)
        if key:
            return self._field_answer(dtype, key, fields, spec), {"route": "field", "field": key}
        if foreign:
            hit = None if re.search(r"значение поля|укажи|назови", q) else self.index.search(question, min_score=0.5)  # напр. п. 4.3: печать для заявления не требуется
            if hit and hit[0] not in self.not_established:
                cid = hit[0]
                return (rec(True, self.index.text(cid), f"Согласно пункту {cid} Положения: {self.index.text(cid)}", [f"rule:{cid}"]),
                        {"route": "rule_search", "rules": [cid], "score": round(hit[1], 3)})
            text = (f"В документе типа «{self.types[dtype]['title']}» нет поля «{foreign}». "
                    "Обратитесь в деканат.")
            return rec(False, None, text, []), {"route": "foreign_field", "label": foreign}

        # 4. вопрос по тексту Положения
        hit = self.index.search(question)
        if hit:
            cid, score = hit
            if cid in self.not_established:
                text = ("Положением это не установлено: " + self.index.text(cid).rstrip(".") +
                        ". Обратитесь в деканат.")
                return rec(False, None, text, []), {"route": "rule_not_established", "rules": [cid], "score": round(score, 3)}
            text = f"Согласно пункту {cid} Положения: {self.index.text(cid)}"
            return rec(True, self.index.text(cid), text, [f"rule:{cid}"]), {"route": "rule_search", "rules": [cid], "score": round(score, 3)}

        # 5. ответа нет (п. 2.4, 6.3)
        return rec(False, None, NO_INFO, []), {"route": "no_info"}

    def _completeness(self, dtype, fields, val):
        spec = self.types[dtype]["fields"]
        refs = self._rule_refs(val["sources"])
        pts = ", ".join(val["sources"])
        if val["status"] == "document_ok":
            text = (f"Документ содержит все обязательные сведения по пунктам {pts} Положения. "
                    "Окончательное решение примет сотрудник деканата.")
        else:
            names = ", ".join(spec[k]["label"] if spec[k]["label"].startswith("ФИО") else norm_text(spec[k]["label"]) for k in val["missing_fields"])
            text = (f"Не хватает следующих сведений: {names}. Основание: пункты {pts} Положения. "
                    "Окончательное решение примет сотрудник деканата.")
        return {"question_id": None, "answerable": True, "value": val["status"], "answer": text, "sources": refs}

    def _field_answer(self, dtype, key, fields, spec):
        f, v = spec[key], fields[key]
        base = {"question_id": None}
        if f["kind"] == "mark":
            present = v is True
            text = (f"{f['label']}: в документе есть." if present
                    else f"{f['label']}: в документе не обнаружена (графическая отметка отсутствует). "
                         f"Это обязательный элемент по пункту {f['rule']} Положения.")
            return {**base, "answerable": True, "value": "да" if present else "нет",
                    "answer": text, "sources": [f"field:{key}"]}
        if v == NOT_FOUND:
            return {**base, "answerable": False, "value": None,
                    "answer": f"Поле «{f['label']}» не найдено в документе. Обратитесь в деканат.", "sources": []}
        return {**base, "answerable": True, "value": v, "answer": f"{f['label']}: {v}.", "sources": [f"field:{key}"]}

    # ---- пакетная обработка документа
    def process_document(self, card, questions):
        dtype, fields = self.normalize_card(card)
        answers = []
        for q in questions:
            a = self.answer(card, q["question"], q["question_id"])
            answers.append(a)
        return {"document_id": card["document_id"], "document_type": dtype, "fields": fields,
                "validation": self.validation_record(card), "answers": answers}


# ----------------------------------------------------------------------------- CLI
def cmd_batch(a):
    rag = DeanRAG()
    cards = json.loads(Path(a.cards).read_text(encoding="utf-8"))
    if isinstance(cards, dict):
        cards = cards.get("documents", [cards])
    questions = json.loads(Path(a.questions).read_text(encoding="utf-8"))
    qs = {}
    for q in questions:
        qs.setdefault(q["document_id"], []).append(q)
    docs = [rag.process_document(c, qs.get(c["document_id"], [])) for c in cards]
    out = {"version": "1.0", "documents": docs}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Готово: {len(docs)} документов -> {a.out}")


def cmd_ask(a):
    rag = DeanRAG()
    card = json.loads(Path(a.card).read_text(encoding="utf-8"))
    ans, trace = rag.answer_with_trace(card, a.question, "cli")
    print(json.dumps({"answer": ans, "trace": trace}, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("batch", help="карточки OCR + questions.json -> results.json")
    b.add_argument("--cards", required=True); b.add_argument("--questions", required=True)
    b.add_argument("--out", default="results.json"); b.set_defaults(fn=cmd_batch)
    s = sub.add_parser("ask", help="один вопрос по одной карточке")
    s.add_argument("--card", required=True); s.add_argument("--question", required=True); s.set_defaults(fn=cmd_ask)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
