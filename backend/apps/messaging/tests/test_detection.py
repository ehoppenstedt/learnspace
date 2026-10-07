import pytest

from apps.messaging.detection import detect


@pytest.mark.parametrize("text,kinds", [
    ("Mi cel es 55 1234 5678", {"phone"}),
    ("márcame al cinco cinco uno dos tres cuatro cinco seis siete ocho", {"phone"}),
    ("escríbeme a ana.lopez@gmail.com", {"email"}),
    ("ana arroba gmail punto com", {"email"}),
    ("mira www.miestudio.mx", {"link"}),
    ("deposítame a la CLABE 012180001234567891", {"payment"}),
    ("mejor por whats", {"social"}),
    ("sígueme en insta @taller.luz", {"social"}),
])
def test_detects_contact_and_payment(text, kinds):
    assert kinds <= set(detect(text))


@pytest.mark.parametrize("text", [
    "¿La clase es apta para principiantes?",
    "Llego a las 7:30, somos 2 personas",
    "¿Cuánto cuesta el material? ¿$250?",
    "Nos vemos el 12 de octubre a las 19:00",
])
def test_ordinary_questions_pass(text):
    assert detect(text) == []
