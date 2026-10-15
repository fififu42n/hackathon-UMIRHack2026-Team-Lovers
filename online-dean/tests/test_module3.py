#!/usr/bin/env python3
"""Тесты модуля 3: python3 test_module3.py"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dean_rag import DeanRAG, to_iso_date

rag = DeanRAG()
fails = 0
def check(name, cond, info=""):
    global fails
    if not cond:
        fails += 1; print("FAIL", name, info)

# --- 1. грязный выход OCR: форматы дат, регистр, пустые значения, курс с текстом
card = {"document_id": "t1", "document_type": "academic_leave_application",
        "fields": {"student_name": " Иванов Иван Иванович ", "group": "", "course": "2 курс",
                   "leave_reason": "Не найдено", "leave_start": "1 сентября 2026 года",
                   "leave_end": "31.08.2027", "application_date": None, "signature_present": True}}
dtype, f = rag.normalize_card(card)
check("date long", f["leave_start"] == "2026-09-01", f)
check("date dots", f["leave_end"] == "2027-08-31", f)
check("course", f["course"] == "2", f)
check("missing", f["group"] == f["leave_reason"] == f["application_date"] == "не найдено", f)
v = rag.validation_record(card)
check("validation", v == {"status": "missing_fields", "missing_fields": ["group", "leave_reason", "application_date"],
                          "sources": ["rule:4.1"]}, v)
check("iso", to_iso_date("5 января 2027 г.") == "2027-01-05")

# --- 2. перефразированные вопросы
study = {"document_id": "t2", "document_type": "study_certificate",
         "fields": {"student_name": "Петров П.П.", "university": "Учебный университет «Меридиан»", "program": "38.03.01 Экономика",
                    "study_form": "очная", "study_start": "2023-09-01", "study_end": "2026-08-31", "document_number": "ОБ-1",
                    "issue_date": "не найдено", "signature_present": True, "seal_present": False}}
cases = [
    (study, "Хватит ли этой справки? Чего не хватает?", True, "missing_fields", ["rule:3.1", "rule:3.3"]),
    (study, "Хватит ли справки для перевода на 2 курс?", True, "missing_fields", ["rule:3.1", "rule:3.3"]),
    (study, "Подойдёт ли эта справка?", True, "missing_fields", ["rule:3.1", "rule:3.3"]),
    (study, "Всё ли в порядке с документом?", True, "missing_fields", ["rule:3.1", "rule:3.3"]),
    (study, "Кто решает, принят ли мой документ?", True, "сотрудник деканата", ["rule:1.3"]),
    (study, "Принят ли документ?", True, "сотрудник деканата", ["rule:1.3"]),
    (study, "Когда закончится обучение?", True, "2026-08-31", ["field:study_end"]),
    (study, "В каком вузе выдана справка?", True, "Учебный университет «Меридиан»", ["field:university"]),
    (study, "Какой номер справки?", True, "ОБ-1", ["field:document_number"]),
    (study, "Какая дата выдачи?", False, None, []),
    (study, "Есть ли печать на справке?", True, "нет", ["field:seal_present"]),
    (study, "Укажи значение поля «Группа»", False, None, []),   # поля нет в этом типе
    # --- ловушки
    (study, "Какова стоимость обучения за следующий семестр?", False, None, []),
    (study, "Какой размер стипендии положен студенту?", False, None, []),
    (study, "Какой срок рассмотрения документа деканатом?", False, None, []),
    (study, "По какому номеру телефона можно связаться с деканатом?", False, None, []),
    (study, "В каком кабинете принимают оригиналы документов?", False, None, []),
    (study, "Как перевестись на второй курс?", False, None, []),
    (study, "Какая погода в Москве?", False, None, []),
    (study, "Сколько академических задолженностей допустимо?", False, None, []),   # п. 3.5: не установлено
    (card, "Какова максимальная длительность отпуска?", False, None, []),            # п. 4.4: не установлено
    (card, "Нужна ли печать вуза для заявления?", True, None, ["rule:4.3"]),
    ({"document_id":"t3","document_type":"internship_certificate","fields":{"supervisor_name":"Захаров И.П.","signature_present":False,"seal_present":True}},
     "Есть ли подпись руководителя?", True, "нет", ["field:signature_present"]),
    ({"document_id":"t3","document_type":"internship_certificate","fields":{"supervisor_name":"Захаров И.П.","signature_present":False,"seal_present":True}},
     "Укажи ФИО руководителя практики", True, "Захаров И.П.", ["field:supervisor_name"]),
    (card, "На какой курс?", True, "2", ["field:course"]),
]
for c, q, ans, val, src in cases:
    a = rag.answer(c, q, "x")
    ok = a["answerable"] == ans and sorted(a["sources"]) == sorted(src) and (val is None or a["value"] == val)
    if ans is False:
        ok = ok and a["value"] is None and a["sources"] == []
    check(q, ok, a)
    check(q + " [answer text]", isinstance(a["answer"], str) and a["answer"].strip())

print("OK, все тесты пройдены" if not fails else f"Провалено: {fails}")
sys.exit(1 if fails else 0)
