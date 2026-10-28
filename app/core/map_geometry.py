"""MapLibre's straight Mercator segments, independent of the SQL graph model."""
import hashlib
import json
import math

from core.map_domain import MapOperationError

MERCATOR_LIMIT = 85.0511287798066


def geometry_token(points):
    # Includes live endpoint coordinates: moving a building does not bump a
    # connection's version. This is a snapshot, not an authorization token.
    canonical = None if points is None else [[round(float(x), 7), round(float(y), 7)] for x, y in points]
    return hashlib.sha256(json.dumps(canonical, separators=(",", ":")).encode()).hexdigest()


def mercator(point):
    lng, lat = point
    if abs(lat) > MERCATOR_LIMIT:
        raise MapOperationError("unsupported_projection", "Вставка доступна в пределах проекции карты.", status=422)
    return math.radians(lng), math.asinh(math.tan(math.radians(lat)))


def segment_position(a, b, fraction):
    ax, ay = mercator(a)
    bx, by = mercator(b)
    if abs(b[0] - a[0]) > 180:
        raise MapOperationError("unsupported_projection", "Сначала разделите трассу у линии перемены дат.", status=422)
    return [math.degrees(ax + fraction * (bx - ax)), math.degrees(math.atan(math.sinh(ay + fraction * (by - ay))))]
