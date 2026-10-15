NOT_FOUND = "не найдено"

DOC_TYPES = {
    "study_certificate": {
        "keywords": ["об обучении", "форма обучения", "период обучения", "вуза"],
        "rules": {"text": "rule:3.1", "signature_present": "rule:3.2", "seal_present": "rule:3.3"},
        "fields": {
            "student_name": {"kind": "name", "labels": ["ФИО студента"]},
            "university": {"kind": "quoted", "labels": ["Название вуза"]},
            "program": {"kind": "text", "labels": ["Направление подготовки"]},
            "study_form": {"kind": "text", "labels": ["Форма обучения"]},
            "study_start": {"kind": "date", "labels": ["Начало периода обучения"],
                            "period_labels": ["Период обучения"], "period_index": 0},
            "study_end": {"kind": "date", "labels": ["Окончание периода обучения"],
                          "period_labels": ["Период обучения"], "period_index": 1},
            "document_number": {"kind": "code", "labels": ["Номер справки"]},
            "issue_date": {"kind": "date", "labels": ["Дата выдачи"]},
            "signature_present": {"kind": "mark"},
            "seal_present": {"kind": "mark"},
        },
    },
    "academic_leave_application": {
        "keywords": ["академическ", "отпуск", "заявлени"],
        "rules": {"text": "rule:4.1", "signature_present": "rule:4.2"},
        "fields": {
            "student_name": {"kind": "name", "labels": ["ФИО студента"]},
            "group": {"kind": "text", "labels": ["Учебная группа", "Группа"]},
            "course": {"kind": "number", "labels": ["Курс"]},
            "leave_reason": {"kind": "text", "labels": ["Причина отпуска"]},
            "leave_start": {"kind": "date", "labels": ["Дата начала отпуска"]},
            "leave_end": {"kind": "date", "labels": ["Дата окончания отпуска"]},
            "application_date": {"kind": "date", "labels": ["Дата заявления"]},
            "signature_present": {"kind": "mark"},
        },
    },
    "internship_certificate": {
        "keywords": ["практик", "руководител", "организаци"],
        "rules": {"text": "rule:5.1", "signature_present": "rule:5.2", "seal_present": "rule:5.3"},
        "fields": {
            "student_name": {"kind": "name", "labels": ["ФИО студента"]},
            "organization": {"kind": "quoted", "labels": ["Название организации"]},
            "internship_start": {"kind": "date", "labels": ["Дата начала практики"]},
            "internship_end": {"kind": "date", "labels": ["Дата окончания практики"]},
            "supervisor_name": {"kind": "name", "labels": ["ФИО руководителя практики"]},
            "grade": {"kind": "text", "labels": ["Оценка"]},
            "document_number": {"kind": "code", "labels": ["Номер справки"]},
            "issue_date": {"kind": "date", "labels": ["Дата выдачи"]},
            "signature_present": {"kind": "mark"},
            "seal_present": {"kind": "mark"},
        },
    },
}