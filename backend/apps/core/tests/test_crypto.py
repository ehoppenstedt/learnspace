import base64
import os

import pytest
from cryptography.exceptions import InvalidTag
from django.db import connection

from apps.core import crypto
from apps.core.geo import haversine_m, public_point
from apps.core.ids import uuid7
from conftest import point


def _key():
    return base64.b64encode(os.urandom(32)).decode()


def test_roundtrip_and_tamper_detection(settings):
    settings.FIELD_ENCRYPTION_KEYS = f"k1:{_key()}"
    blob = crypto.encrypt("silla de ruedas")
    assert b"silla" not in blob
    assert crypto.decrypt(blob) == "silla de ruedas"
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(InvalidTag):
        crypto.decrypt(tampered)


def test_key_rotation_old_ciphertext_still_decrypts(settings):
    old = _key()
    settings.FIELD_ENCRYPTION_KEYS = f"old:{old}"
    blob = crypto.encrypt("dato sensible")
    settings.FIELD_ENCRYPTION_KEYS = f"new:{_key()},old:{old}"
    assert crypto.decrypt(blob) == "dato sensible"
    assert crypto.encrypt("x").startswith(b"v1:new:")


@pytest.mark.django_db
def test_accessibility_needs_are_encrypted_at_rest(learner):
    profile = learner.learner_profile
    profile.accessibility_needs = "Uso silla de ruedas"
    profile.save()
    with connection.cursor() as cur:
        cur.execute("SELECT accessibility_needs FROM accounts_learnerprofile WHERE user_id = %s", [learner.pk])
        raw = bytes(cur.fetchone()[0])
    assert b"silla" not in raw
    profile.refresh_from_db()
    assert profile.accessibility_needs == "Uso silla de ruedas"


def test_public_point_is_stable_and_150_to_450m_away():
    exact = point(19.4194, -99.1617)
    a = public_point(exact, "space-1")
    assert public_point(exact, "space-1") == a
    assert 140 <= haversine_m(exact, a) <= 460
    assert public_point(exact, "space-2") != a


def test_uuid7_is_time_ordered_and_versioned():
    ids = [uuid7() for _ in range(50)]
    assert all(u.version == 7 for u in ids)
    assert [u.int >> 80 for u in ids] == sorted(u.int >> 80 for u in ids)

