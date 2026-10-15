import os
from ocr_engine import recognize
from cleanup import normalize_text
from extract import detect_doc_type, parse_fields, validate
from marks import detect_marks
from doc_types import DOC_TYPES

MIN_TEXT_LEN = 30  # короче - считаем, что снимок нечитаем (бонус «плохие снимки»)


def process_document(file_path, doc_type=None, document_id=None, debug_dir=None, with_text=False):
    """Модуль 2: файл -> карточка полей. with_text=True вернёт (карточка, распознанный_текст)."""
    raw_text = recognize(file_path)
    text = normalize_text(raw_text)

    name = document_id or os.path.basename(file_path)
    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)
        with open(os.path.join(debug_dir, name + ".txt"), "w", encoding="utf-8") as f:
            f.write(text)

    if len(text.strip()) < MIN_TEXT_LEN:
        raise ValueError("Текст на изображении почти не распознан: документ сфотографирован неправильно или нечитаем")

    if doc_type is None:
        doc_type = detect_doc_type(text)
    if doc_type not in DOC_TYPES:
        raise ValueError("Не удалось определить тип документа. Выберите тип вручную")

    fields = parse_fields(text, doc_type)
    signature, seal = detect_marks(file_path)
    for key, cfg in DOC_TYPES[doc_type]["fields"].items():
        if cfg["kind"] == "mark":
            fields[key] = signature if key == "signature_present" else seal

    doc = {
        "document_id": name,
        "document_type": doc_type,
        "fields": fields,
        "validation": validate(doc_type, fields),
        "answers": [],
    }
    return (doc, text) if with_text else doc


def for_module3(result):
    return {
        "document_id": result["document_id"],
        "document_type": result["document_type"],
        "fields": result["fields"],
    }
