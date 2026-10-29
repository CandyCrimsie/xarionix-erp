"""Strict segment metadata and fixed geographical anchors, not inventory."""
import math

from core.map_domain import MapOperationError
from core.map_geometry import geometry_token, mercator, segment_position

INSTALLATION_METHODS = ("unknown", "aerial", "duct", "direct_buried", "facade", "indoor")
INSTALLATION_CHECK = """jsonb_typeof(installation_methods) = 'array'
    AND (jsonb_array_length(installation_methods) = 0 OR
         jsonb_array_length(installation_methods) = jsonb_array_length(vertices) + 1)
    AND installation_methods <@ '["unknown","aerial","duct","direct_buried","facade","indoor"]'::jsonb"""


def methods_for(vertices, methods):
    return list(methods) if methods else ["unknown"] * (len(vertices) + 1)


def split_parts(points, methods, index, position):
    left, right = points[:index + 1], points[index + 1:]
    before, after = methods[:index + 1], methods[index:]
    if left[-1] == position:
        left, before = left[:-1], before[:-1]
    if right[0] == position:
        right, after = right[1:], after[1:]
    return ([*left, position], before), ([position, *right], after)


def locate_anchor(points, marker, attachment=None):
    """Index is valid only for its exact snapshot; otherwise reproject the fixed
    marker position. Refuse ambiguous crossings rather than guessing a branch.
    """
    from services.map_connections import route_length
    position = [float(marker.longitude), float(marker.latitude)]
    if attachment is not None and attachment.geometry_token == geometry_token(points):
        index, fraction = attachment.segment_index, float(attachment.fraction)
        if index < len(points) - 1 and route_length([segment_position(points[index], points[index + 1], fraction), position]) <= .05:
            return index, fraction
    px, py = mercator(position)
    matches = []
    for index, (a, b) in enumerate(zip(points, points[1:])):
        ax, ay = mercator(a)
        bx, by = mercator(b)
        dx, dy = bx - ax, by - ay
        if dx * dx + dy * dy < 1e-24:
            continue
        fraction = max(0., min(1., ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        if route_length([segment_position(a, b, fraction), position]) <= .05:
            progress = index + fraction
            if not matches or abs(progress - (matches[-1][0] + matches[-1][1])) > 1e-5:
                matches.append((index, fraction))
    if len(matches) != 1:
        raise MapOperationError("route_anchor_conflict", "На изменяемом участке закреплён объект. Сохраните его точку на трассе или явно отвяжите объект перед правкой.")
    return matches[0]


def add_boundary(points, methods, index, fraction, position, after_method, until="end"):
    if points[index] == position:
        boundary = index
    elif points[index + 1] == position:
        boundary = index + 1
    else:
        points = [*points[:index + 1], position, *points[index + 1:]]
        methods = [*methods[:index + 1], methods[index], *methods[index + 1:]]
        boundary = index + 1
    methods = list(methods)
    for i in range(boundary, len(methods) if until == "end" else min(boundary + 1, len(methods))):
        methods[i] = after_method
    if len(points) > 500:
        raise MapOperationError("vertex_limit", "Допускается не более 498 промежуточных вершин.", status=422)
    return points, methods


def path_offset(points, index, fraction):
    projected = [mercator(point) for point in points]
    lengths = [math.dist(a, b) for a, b in zip(projected, projected[1:])]
    return sum(lengths[:index]) + lengths[index] * fraction


def offset_segment(points, offset):
    for index, (a, b) in enumerate(zip(points, points[1:])):
        length = math.dist(mercator(a), mercator(b))
        if length > 1e-15 and (offset <= length or index == len(points) - 2):
            return index, max(0., min(1., offset / length))
        offset -= length
    raise MapOperationError("degenerate_route", "Трасса не содержит ненулевых сегментов.", status=422)


def edit_boundary(points, methods, vertex, operation, *, position=None, index=None, fraction=None, method=None, keep=None):
    """Boundaries are changes between edge attributes, never physical nodes.

    Retain every old corner, including the former boundary. Moving inserts at
    most one collinear vertex; deleting only merges attributes, not geometry.
    """
    from services.map_connections import route_length
    boundaries = [i for i in range(1, len(methods)) if methods[i - 1] != methods[i]]
    if vertex not in boundaries:
        raise MapOperationError("boundary_not_found", "Граница прокладки отсутствует. Обновите трассу.", status=409)
    previous = max((i for i in boundaries if i < vertex), default=0)
    following = min((i for i in boundaries if i > vertex), default=len(methods))
    before, after = methods[vertex - 1], methods[vertex]
    points, methods = list(points), list(methods)
    if operation == "set":
        methods[vertex:following] = [method] * (following - vertex)
    elif operation == "remove":
        value = before if keep == "previous" else after
        methods[previous:following] = [value] * (following - previous)
    else:
        offset = path_offset(points, index, fraction)
        if not path_offset(points, previous, 0) < offset < path_offset(points, following - 1, 1):
            raise MapOperationError("boundary_order", "Граница не может пересекать соседние границы.", status=422)
        inserted = False
        if position == points[index]:
            target = index
        elif position == points[index + 1]:
            target = index + 1
        else:
            target, inserted = index + 1, True
            points.insert(target, position)
            methods.insert(target, methods[index])
        if inserted:
            previous += int(target <= previous)
            following += int(target <= following)
        if route_length(points[previous:target + 1]) < 1 or route_length(points[target:following + 1]) < 1:
            raise MapOperationError("boundary_too_close", "Между границами должен оставаться участок не короче 1 м.", status=422)
        if len(points) > 500:
            raise MapOperationError("vertex_limit", "Допускается не более 498 промежуточных вершин.", status=422)
        methods[previous:target] = [before] * (target - previous)
        methods[target:following] = [after] * (following - target)
    return points, methods
