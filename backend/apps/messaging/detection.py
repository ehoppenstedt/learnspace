"""Detects contact and off-platform payment details in chat messages.

Purpose: before a booking exists, warn the sender (and record it) when they try to move the
conversation or the payment off the platform. Tuned for Mexico; false positives only cost a
confirmation tap, false negatives cost a take-rate leak, so it leans inclusive.
"""

import re
import unicodedata

KINDS = ("phone", "email", "link", "payment", "social")

_DIGIT_WORDS = {
    "cero": "0", "uno": "1", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5", "seis": "6", "siete": "7",
    "ocho": "8", "nueve": "9",
}
_EMAIL = re.compile(
    r"[\w.+-]+(@|\s*\(at\)\s*|\s*\[at\]\s*|\s+arroba\s+)[\w-]+(\.|\s*\(dot\)\s*|\s+punto\s+)[a-z]{2,}", re.I)
_LINK = re.compile(r"(https?://|www\.)\S+|\b[\w-]+\.(com|mx|net|org|io|me|link|ly)(/\S*)?\b", re.I)
_PAYMENT = re.compile(
    r"\b(clabe|spei|transferencia|dep[oó]sito|deposita|paypal|mercado\s*pago|mercadopago|oxxo|clip\.mx|"
    r"pago\s+directo|p[aá]game|en\s+efectivo|cash)\b",
    re.I,
)
_SOCIAL = re.compile(
    r"\b(whats\s*app|whatsapp|whats|wasap|guasap|wa\.me|telegram|t\.me|instagram|insta|signal|facebook|fb)\b"
    r"|(^|\s)@[a-z0-9_.]{3,}", re.I)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    # "cinco cinco uno dos..." -> digits; people spell numbers out to dodge filters.
    for word, digit in _DIGIT_WORDS.items():
        text = re.sub(rf"\b{word}\b", digit, text)
    return text


def _digit_runs(text: str) -> list[str]:
    # Digits possibly separated by spaces, dots, dashes or parentheses.
    return ["".join(ch for ch in m.group() if ch.isdigit()) for m in re.finditer(r"[\d][\d\s().\-]{6,}[\d]", text)]


def detect(text: str) -> list[str]:
    norm = _normalize(text)
    found = set()
    for digits in _digit_runs(norm):
        if len(digits) == 18:
            found.add("payment")  # CLABE
        elif 13 <= len(digits) <= 19:
            found.add("payment")  # card number
        elif 8 <= len(digits) <= 12:
            found.add("phone")
    if _EMAIL.search(norm):
        found.add("email")
    if _LINK.search(norm) and "email" not in found:
        found.add("link")
    if _PAYMENT.search(norm):
        found.add("payment")
    if _SOCIAL.search(norm):
        found.add("social")
    return [k for k in KINDS if k in found]
