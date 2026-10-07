"""Location privacy: a stable, deterministic public point near the real one."""

import hashlib
import math

from django.contrib.gis.geos import Point

EARTH_RADIUS_M = 6_371_000
MIN_OFFSET_M = 150
MAX_OFFSET_M = 450


def public_point(exact: Point, salt: str) -> Point:
    """Offset `exact` by 150-450 m in a direction derived from `salt` (e.g. the space id).

    Deterministic so the same space always shows the same approximate pin; re-randomizing
    on every request would let anyone average the pins back to the real address.
    """
    digest = hashlib.sha256(salt.encode()).digest()
    bearing = int.from_bytes(digest[:4], "big") / 2**32 * 2 * math.pi
    distance = MIN_OFFSET_M + int.from_bytes(digest[4:8], "big") / 2**32 * (MAX_OFFSET_M - MIN_OFFSET_M)
    lat1, lng1 = math.radians(exact.y), math.radians(exact.x)
    ang = distance / EARTH_RADIUS_M
    lat2 = math.asin(math.sin(lat1) * math.cos(ang) + math.cos(lat1) * math.sin(ang) * math.cos(bearing))
    lng2 = lng1 + math.atan2(
        math.sin(bearing) * math.sin(ang) * math.cos(lat1), math.cos(ang) - math.sin(lat1) * math.sin(lat2)
    )
    return Point(round(math.degrees(lng2), 6), round(math.degrees(lat2), 6), srid=4326)


def haversine_m(a: Point, b: Point) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (a.y, a.x, b.y, b.x))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))
