# Онлайн-деканат: сборка модулей

Студент загружает фото/скан/PDF и (необязательно) вопрос → сервис показывает распознанный текст,
карточку полей, предварительную проверку комплектности и ответ со ссылками на пункты Положения.
Решение о принятии документа принимает сотрудник деканата.

## Состав
| Часть | Файлы |
|---|---|
| Модуль 2: OCR, поля, подпись/печать | `ocr_engine.py`, `cleanup.py`, `extract.py`, `marks.py`, `doc_types.py`, `pipeline.py`|
| Модуль 3: ответы по Положению | `dean_rag.py`, `doc_types.json`, `rules.md` |
| Сервер (склейка) | `app.py` |
| Фронтенд | `frontend/index.html`, `frontend/static/{index.css,app.js}` |
| Сдача | `run_closed.py` (OCR → RAG → `results.json`), `dataset/evaluate.py` |

Всё локально, без внешних API. Зависимости: `requirements.txt` (easyocr + torch, pymupdf, numpy, scipy, pillow, flask).
Требуется Python 3.10–3.12 (на 3.15 зависимости пока не устанавливаются).
Модель easyocr (ru, en) скачивается при первом распознавании.

## Запуск
```sh
pip install -r requirements.txt
python3 app.py                      # http://localhost:5000  (порт: переменная PORT)
```

## Результат для сдачи
```sh
python3 run_closed.py --base dataset --source image --profile fast     # или --base <закрытый набор>
python3 dataset/evaluate.py --reference dataset/reference_results.json --predictions results.json
```
`run_closed.py` не читает эталон. Ошибки по отдельным файлам пишутся в `errors.txt`, прогон не прерывается.

## API
| Метод | Путь | Назначение |
|---|---|---|
| POST | `/api/analyze` | multipart: `file`, `question?`, `document_type?` (`auto` или тип) → OCR-текст, карточка, проверка, ответ, цитаты |
| POST | `/api/answer` | новый вопрос по готовой карточке (без повторного OCR) |
| POST | `/api/check` | проверка без вопроса |
| GET | `/api/schema/<тип>`, `/api/types`, `/api/rules[/<id>]`, `/health` | справочное |

Нечитаемый снимок или неопределённый тип → 422 с понятным текстом (его показывает блок ошибки на странице).

## Тесты
```sh
python3 tests/test_module3.py        # RAG-модуль
python3 tests/test_integration.py    # вся цепочка с подменой OCR: 1.0 по всем метрикам evaluate.py
```
