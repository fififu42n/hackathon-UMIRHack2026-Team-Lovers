import itertools
import os
import re
from difflib import get_close_matches

DIGIT_VARIANTS = {"0": "о", "3": "зв", "4": "ч", "6": "б", "8": "в"}

TOKEN = re.compile(r"[0-9А-Яа-яЁё]+")
LETTER = re.compile(r"[А-Яа-яЁё]")
DIGIT = re.compile(r"[0-9]")

WORDS_FILE = os.path.join(os.path.dirname(__file__), "known_words.txt")


def load_known_words():
    if not os.path.exists(WORDS_FILE):
        return set()
    with open(WORDS_FILE, encoding="utf-8") as f:
        return {line.strip().lower() for line in f if line.strip()}


KNOWN = load_known_words()


def restore_case(original, new):
    return new.capitalize() if original[:1].isupper() else new


def fix_digits(match):
    word = match.group(0)
    if not (LETTER.search(word) and DIGIT.search(word)):
        return word

    options = [DIGIT_VARIANTS.get(ch, ch) for ch in word.lower()]
    candidates = ["".join(c) for c in itertools.islice(itertools.product(*options), 64)]
    for candidate in candidates:
        if candidate in KNOWN:
            return restore_case(word, candidate)
    return restore_case(word, candidates[0])


def fuzzy_fix(word, cutoff=0.7):
    low = word.lower()
    if low in KNOWN or len(low) < 4 or not KNOWN:
        return word
    matches = get_close_matches(low, KNOWN, n=1, cutoff=cutoff)
    return restore_case(word, matches[0]) if matches else word


def clean_name(value, use_fuzzy=False):
    words = []
    for word in value.split():
        word = TOKEN.sub(fix_digits, word)
        if use_fuzzy:
            word = fuzzy_fix(word)
        words.append(word)
    return " ".join(words)


def normalize_text(text):
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" +([,.!?;:])", r"\1", text)
    return text.strip()

LATIN_TO_CYRILLIC = {
    "a": "а", "c": "с", "e": "е", "o": "о", "p": "р", "x": "х", "y": "у",
    "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "K": "К", "M": "М",
    "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "У",
}

LETTER_TO_DIGIT = {"О": "0", "о": "0", "O": "0", "o": "0", "З": "3", "з": "3",
                   "Ч": "4", "б": "6", "В": "8", "I": "1", "l": "1"}


def fix_latin(value):
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", value))
    latin = len(re.findall(r"[A-Za-z]", value))
    if cyrillic <= latin:
        return value
    return "".join(LATIN_TO_CYRILLIC.get(ch, ch) for ch in value)


def fix_quoted(value):
    if re.fullmatch(r"\S+ \S+ «[^«»]+»", value):
        return value
    parts = value.split(None, 2)
    if len(parts) < 3:
        return value
    first, second, rest = parts
    name = rest.strip()[1:-1].strip()
    return f"{first} {second} «{name}»" if name else value


def fix_code(value):
    value = fix_latin(value.strip())
    match = re.fullmatch(r"([^\W\d_]+)\s*[-–—]\s*(\S+)", value)
    if not match:
        return value
    prefix, number = match.groups()
    number = "".join(LETTER_TO_DIGIT.get(ch, ch) for ch in number)
    return f"{prefix}-{number}"