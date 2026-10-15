import re
from cleanup import clean_name, fix_latin, fix_quoted, fix_code
from doc_types import DOC_TYPES, NOT_FOUND

MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

DATE_ANY = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})"
    r"|(\d{1,2})[./](\d{1,2})[./](\d{4})"
    r"|(\d{1,2})\s+([А-Яа-яЁё]+)\s+(\d{4})"
)


def find_dates(text):
    dates = []
    for m in DATE_ANY.finditer(text):
        if m.group(1):
            year, month, day = m.group(1), m.group(2), m.group(3)
        elif m.group(4):
            day, month, year = m.group(4), m.group(5), m.group(6)
        else:
            month = MONTHS.get(m.group(8).lower())
            if not month:
                continue
            day, year = m.group(7), m.group(9)
        dates.append(f"{int(year):04d}-{int(month):02d}-{int(day):02d}")
    return dates


def find_after_label(text, labels):
    for label in labels:
        pattern = r"^[ \t]*" + re.escape(label) + r"[ \t]*[:–—-]?[ \t]*([^\n]*)"
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            value = match.group(1).strip()
            if re.fullmatch(r"[\s_\-–—.|~=]*", value):
                return ""
            return value
    return None

def fix_quotes(value):
    value = re.sub(r"(?<![А-Яа-яЁё])к(?=[А-ЯЁ])", "«", value)
    value = re.sub(r"(?<=[А-Яа-яЁё])>", "»", value)
    return value.replace("<", "«")

def read_date(text, value, cfg):
    if value is None and "period_labels" in cfg:
        period = find_after_label(text, cfg["period_labels"]) or ""
        dates = find_dates(period)
        index = cfg["period_index"]
        return dates[index] if len(dates) > index else NOT_FOUND
    dates = find_dates(value or "")
    return dates[0] if dates else NOT_FOUND


def parse_fields(text, doc_type):
    fields = {}
    for key, cfg in DOC_TYPES[doc_type]["fields"].items():
        kind = cfg["kind"]
        if kind == "mark":
            continue
        value = find_after_label(text, cfg["labels"])
        if kind == "date":
            fields[key] = read_date(text, value, cfg)
        elif not value:
            fields[key] = NOT_FOUND
        elif kind == "name":
            fields[key] = clean_name(fix_latin(value))
        elif kind == "quoted":
            fields[key] = fix_quoted(fix_latin(value))
        elif kind == "code":
            fields[key] = fix_code(value)
        elif kind == "number":
            digits = re.search(r"\d+", value)
            fields[key] = digits.group(0) if digits else NOT_FOUND
        else:
            fields[key] = fix_quotes(fix_latin(value))
    return fields


def detect_doc_type(text):
    low = text.lower()
    scores = {
        type_id: sum(word in low for word in cfg["keywords"])
        for type_id, cfg in DOC_TYPES.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def validate(doc_type, fields):
    rules = DOC_TYPES[doc_type]["rules"]
    missing = []
    sources = set()
    for key, value in fields.items():
        if value == NOT_FOUND or value is False:
            missing.append(key)
            sources.add(rules.get(key, rules["text"]))
    if not missing:
        return {"status": "document_ok", "missing_fields": [], "sources": sorted(rules.values())}
    return {"status": "missing_fields", "missing_fields": missing, "sources": sorted(sources)}