#!/bin/sh
set -eu

require_value() {
    variable_name="$1"
    eval "variable_value=\${$variable_name:-}"
    if [ -z "$variable_value" ]; then
        echo "map-proxy: $variable_name is required" >&2
        exit 1
    fi
}

require_value YANDEX_TILES_API_KEY
require_value MAP_TILES_SIGNING_SECRET
require_value MAP_TILES_CACHE_SIZE
require_value MAP_TILES_CACHE_TTL
require_value MAP_TILES_CACHE_INACTIVE
require_value MAP_TILES_RPS

case "$YANDEX_TILES_API_KEY" in
    *[!A-Za-z0-9_-]* | "")
        echo "map-proxy: YANDEX_TILES_API_KEY contains unsafe characters" >&2
        exit 1
        ;;
esac

if [ "${#MAP_TILES_SIGNING_SECRET}" -lt 24 ]; then
    echo "map-proxy: MAP_TILES_SIGNING_SECRET must contain at least 24 characters" >&2
    exit 1
fi
if ! printf '%s' "$MAP_TILES_SIGNING_SECRET" \
    | grep -Eq '^[A-Za-z0-9_-]+={0,2}$'; then
    echo "map-proxy: MAP_TILES_SIGNING_SECRET must be URL-safe Base64" >&2
    exit 1
fi

if ! printf '%s' "$MAP_TILES_CACHE_SIZE" \
    | grep -Eq '^[1-9][0-9]*[kKmMgG]$'; then
    echo "map-proxy: MAP_TILES_CACHE_SIZE must be an Nginx size such as 2g" >&2
    exit 1
fi

for duration_name in MAP_TILES_CACHE_TTL MAP_TILES_CACHE_INACTIVE; do
    eval "duration_value=\${$duration_name}"
    if ! printf '%s' "$duration_value" \
        | grep -Eq '^[1-9][0-9]*[smhdw]$'; then
        echo "map-proxy: $duration_name must be an Nginx duration such as 12h" >&2
        exit 1
    fi
done

case "$MAP_TILES_RPS" in
    *[!0-9]* | "")
        echo "map-proxy: MAP_TILES_RPS must be an integer from 1 to 30" >&2
        exit 1
        ;;
esac
if [ "$MAP_TILES_RPS" -lt 1 ] || [ "$MAP_TILES_RPS" -gt 30 ]; then
    echo "map-proxy: MAP_TILES_RPS must be an integer from 1 to 30" >&2
    exit 1
fi
