SUPPORTED_MAP_MARKER_ICONS = frozenset({
    "house",
    "building-2",
    "network",
    "server",
    "router",
    "wifi",
    "map-pin",
    "cable",
    "radio-tower",
    "hard-drive",
    "wrench",
    "zap",
    "circle-alert",
    "map-house", "network-node", "cabinet", "splice", "pole", "chamber", "equipment", "note",
    "fiber-box", "odf", "transition",
})

MAP_MARKER_SIZES = frozenset({"small", "normal", "large"})
MAP_MARKER_SHAPES = frozenset({"circle", "rounded", "pill", "icon"})

MAP_POINT_TYPES = frozenset({"building", "network_node", "cabinet", "splice", "pole", "chamber", "equipment", "note", "fiber_box", "odf", "transition"})
ROUTE_NODE_TYPES = frozenset({"splice", "fiber_box", "odf", "network_node", "cabinet"})
ROUTE_PASS_THROUGH_TYPES = frozenset({"chamber", "pole", "transition", "fiber_box", "network_node", "cabinet"})
POINT_TYPE_CHECK = "point_type IN (" + ", ".join(repr(value) for value in sorted(MAP_POINT_TYPES)) + ")"
