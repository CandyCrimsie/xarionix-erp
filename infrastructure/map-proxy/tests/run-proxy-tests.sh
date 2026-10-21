#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROXY_CONTEXT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
TEST_SUFFIX="$$"
TEST_NETWORK="xarionix-map-proxy-test-$TEST_SUFFIX"
MOCK_CONTAINER="xarionix-map-origin-test-$TEST_SUFFIX"
PROXY_CONTAINER="xarionix-map-proxy-test-$TEST_SUFFIX"
PROXY_IMAGE="xarionix-map-proxy-test:$TEST_SUFFIX"
PROXY_PORT="${MAP_PROXY_TEST_PORT:-18088}"
SIGNING_SECRET="test-map-signing-secret-0123456789abcdef"
TEST_API_KEY="test-yandex-api-key"
RESULT_DIR=$(mktemp -d)

cleanup() {
    docker rm -f "$PROXY_CONTAINER" "$MOCK_CONTAINER" >/dev/null 2>&1 || true
    docker network rm "$TEST_NETWORK" >/dev/null 2>&1 || true
    docker image rm "$PROXY_IMAGE" >/dev/null 2>&1 || true
    rm -rf "$RESULT_DIR"
}
trap cleanup EXIT INT TERM

fail() {
    echo "map-proxy test failed: $1" >&2
    exit 1
}

status_for() {
    method="$1"
    url="$2"
    curl -sS -o /dev/null -w '%{http_code}' -X "$method" "$url"
}

signature_for() {
    expires="$1"
    printf '%s' "$expires map-tiles $SIGNING_SECRET" \
        | openssl dgst -md5 -binary \
        | openssl base64 -A \
        | tr '+/' '-_' \
        | tr -d '='
}

signed_url() {
    path="$1"
    expires="$2"
    signature=$(signature_for "$expires")
    printf 'http://127.0.0.1:%s%s?expires=%s&signature=%s' \
        "$PROXY_PORT" "$path" "$expires" "$signature"
}

docker build -q -t "$PROXY_IMAGE" "$PROXY_CONTEXT" >/dev/null
docker network create "$TEST_NETWORK" >/dev/null

docker run -d --name "$MOCK_CONTAINER" \
    --network "$TEST_NETWORK" \
    --network-alias tiles.api-maps.yandex.ru \
    -v "$SCRIPT_DIR/mock-origin.conf:/etc/nginx/mock.conf:ro" \
    nginx:1.29-alpine sh -c \
    "apk add --no-cache openssl >/dev/null \
      && openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
      -subj '/CN=tiles.api-maps.yandex.ru' \
      -keyout /tmp/mock-key.pem -out /tmp/mock-cert.pem >/dev/null 2>&1 \
      && exec nginx -c /etc/nginx/mock.conf -g 'daemon off;'" >/dev/null

origin_ready=0
for _ in $(seq 1 100); do
    if docker exec "$MOCK_CONTAINER" wget -q --no-check-certificate \
        -O /dev/null 'https://127.0.0.1/v1/tiles/' >/dev/null 2>&1; then
        origin_ready=1
        break
    fi
    sleep 0.1
done
[ "$origin_ready" -eq 1 ] || fail "mock tile origin did not become healthy"

docker run -d --name "$PROXY_CONTAINER" \
    --network "$TEST_NETWORK" \
    -p "127.0.0.1:$PROXY_PORT:8080" \
    -e YANDEX_TILES_API_KEY="$TEST_API_KEY" \
    -e MAP_TILES_SIGNING_SECRET="$SIGNING_SECRET" \
    -e MAP_TILES_CACHE_SIZE=64m \
    -e MAP_TILES_CACHE_TTL=2s \
    -e MAP_TILES_CACHE_INACTIVE=1h \
    -e MAP_TILES_RPS=28 \
    "$PROXY_IMAGE" >/dev/null

ready=0
for _ in $(seq 1 50); do
    if curl -fsS "http://127.0.0.1:$PROXY_PORT/healthz" >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 0.1
done
[ "$ready" -eq 1 ] || fail "proxy did not become healthy"

now=$(date +%s)
valid_expires=$((now + 600))
expired=$((now - 60))

[ "$(status_for GET "http://127.0.0.1:$PROXY_PORT/map/tiles/2/1/1.png")" = 400 ] \
    || fail "missing query parameters were not rejected"
[ "$(status_for GET "http://127.0.0.1:$PROXY_PORT/map/tiles/2/4/1.png?expires=$valid_expires&signature=AAAAAAAAAAAAAAAAAAAAAA")" = 400 ] \
    || fail "out-of-range x coordinate was not rejected before signature verification"
[ "$(status_for GET "$(signed_url '/map/tiles/21/1/1.png' "$valid_expires")")" = 400 ] \
    || fail "zoom above 20 was not rejected"
[ "$(status_for GET "$(signed_url '/map/tiles/2/1/1.png' "$expired")")" = 410 ] \
    || fail "expired permission was not rejected"
[ "$(status_for POST "$(signed_url '/map/tiles/2/1/1.png' "$valid_expires")")" = 405 ] \
    || fail "unsupported method was not rejected"
[ "$(status_for GET "$(signed_url '/map/tiles/2/1/1.png' "$valid_expires")&extra=1")" = 400 ] \
    || fail "unexpected query parameter was not rejected"
[ "$(status_for GET "$(signed_url '/map/tiles/2/-1/1.png' "$valid_expires")")" = 404 ] \
    || fail "negative coordinate was not rejected"
[ "$(status_for GET "http://127.0.0.1:$PROXY_PORT/map/tiles/2/1/%2e%2e.png?expires=$valid_expires&signature=AAAAAAAAAAAAAAAAAAAAAA")" = 404 ] \
    || fail "path traversal attempt was not rejected"
[ "$(status_for GET "http://127.0.0.1:$PROXY_PORT/map/origin/2/1/1.png")" = 404 ] \
    || fail "unexpected endpoint was exposed"

zoom=0
while [ "$zoom" -le 20 ]; do
    maximum=$(((1 << zoom) - 1))
    invalid=$((maximum + 1))
    valid_boundary_status=$(status_for GET \
        "http://127.0.0.1:$PROXY_PORT/map/tiles/$zoom/$maximum/$maximum.png?expires=$valid_expires&signature=AAAAAAAAAAAAAAAAAAAAAA")
    [ "$valid_boundary_status" = 403 ] \
        || fail "valid coordinate boundary was rejected at zoom $zoom"
    invalid_boundary_status=$(status_for GET \
        "http://127.0.0.1:$PROXY_PORT/map/tiles/$zoom/$invalid/$maximum.png?expires=$valid_expires&signature=AAAAAAAAAAAAAAAAAAAAAA")
    [ "$invalid_boundary_status" = 400 ] \
        || fail "invalid coordinate boundary was accepted at zoom $zoom"
    zoom=$((zoom + 1))
done

cache_url=$(signed_url '/map/tiles/10/500/500.png' "$valid_expires")
first_headers="$RESULT_DIR/first-headers"
second_headers="$RESULT_DIR/second-headers"
curl -fsS -D "$first_headers" -o /dev/null "$cache_url"
curl -fsS -D "$second_headers" -o /dev/null "$cache_url"
grep -qi '^X-Tile-Cache: MISS' "$first_headers" || fail "first tile was not a cache miss"
grep -qi '^X-Tile-Cache: HIT' "$second_headers" || fail "second tile was not served from cache"

# A warm tile bypasses the origin limiter entirely. Parallel cache hits must
# remain successful and must not create additional origin requests.
seq 1 100 | xargs -P 20 -I '{}' sh -c \
    'curl -fsS -o /dev/null "$1"' _ "$cache_url"
cached_origin_count=$(docker logs "$MOCK_CONTAINER" 2>&1 \
    | grep -c 'x=500&y=500&z=10' || true)
[ "$cached_origin_count" -eq 1 ] \
    || fail "warm cache produced $cached_origin_count origin requests"

# TTL expiration must trigger exactly one refresh, not serve the old tile
# indefinitely. The test proxy uses a short TTL; production remains 12 hours.
sleep 3
expired_headers="$RESULT_DIR/expired-headers"
curl -fsS -D "$expired_headers" -o /dev/null "$cache_url"
grep -Eqi '^X-Tile-Cache: (EXPIRED|MISS)' "$expired_headers" \
    || fail "expired tile was not refreshed"
refreshed_origin_count=$(docker logs "$MOCK_CONTAINER" 2>&1 \
    | grep -c 'x=500&y=500&z=10' || true)
[ "$refreshed_origin_count" -eq 2 ] \
    || fail "expired tile refresh count was $refreshed_origin_count"

# Cache locking: many requests for the same new tile must result in one origin
# request, not a thundering herd.
locked_url=$(signed_url '/map/tiles/10/501/501.png' "$valid_expires")
seq 1 50 | xargs -P 50 -I '{}' sh -c \
    'curl -fsS -o /dev/null "$1"' _ "$locked_url"
locked_origin_count=$(docker logs "$MOCK_CONTAINER" 2>&1 \
    | grep -c 'x=501&y=501&z=10' || true)
[ "$locked_origin_count" -eq 1 ] \
    || fail "cache lock allowed $locked_origin_count origin requests"

# A single client can issue 100 unique misses without exceeding the origin
# rate. Requests are delayed by the leaky-bucket queue instead of bursting.
single_statuses="$RESULT_DIR/single-statuses"
: > "$single_statuses"
seq 1 100 | while read -r tile; do
    code=$(status_for GET "$(signed_url "/map/tiles/13/$((2000 + tile))/$((2000 + tile)).png" "$valid_expires")")
    printf '%s\n' "$code" >> "$single_statuses"
done
[ "$(grep -c '^200$' "$single_statuses")" -eq 100 ] \
    || fail "single-client scenario did not complete all requests"

# Twenty clients share the same global queue and still complete a bounded
# request set without receiving per-client rate allocations.
parallel_statuses="$RESULT_DIR/parallel-statuses"
: > "$parallel_statuses"
seq 1 80 | xargs -P 20 -I '{}' sh -c '
    tile=$((3000 + $1))
    code=$(curl -sS -o /dev/null -w "%{http_code}" "$2/map/tiles/14/$tile/$tile.png?expires=$3&signature=$4")
    printf "%s\n" "$code" >> "$5"
' _ '{}' "http://127.0.0.1:$PROXY_PORT" "$valid_expires" \
    "$(signature_for "$valid_expires")" "$parallel_statuses"
[ "$(grep -c '^200$' "$parallel_statuses")" -eq 80 ] \
    || fail "twenty-client scenario did not complete all requests"

# 250 parallel unique cache misses exercise the global post-cache limiter.
load_statuses="$RESULT_DIR/load-statuses"
: > "$load_statuses"
seq 1 250 | xargs -P 100 -I '{}' sh -c '
    tile=$((1000 + $1))
    code=$(curl -sS -o /dev/null -w "%{http_code}" "$2/map/tiles/12/$tile/$tile.png?expires=$3&signature=$4")
    printf "%s\n" "$code" >> "$5"
' _ '{}' "http://127.0.0.1:$PROXY_PORT" "$valid_expires" \
    "$(signature_for "$valid_expires")" "$load_statuses"

grep -q '^200$' "$load_statuses" || fail "load test produced no successful responses"
grep -q '^429$' "$load_statuses" || fail "load test did not exercise the rate limiter"

docker logs "$MOCK_CONTAINER" > "$RESULT_DIR/origin.log" 2>&1
python3 - "$RESULT_DIR/origin.log" <<'PY'
import collections
import re
import sys

timestamps_by_zoom = collections.defaultdict(list)
for line in open(sys.argv[1], encoding="utf-8"):
    zoom = re.search(r"[?&]z=(12|13|14)(?:&|\")", line)
    if not zoom:
        continue
    match = re.search(r"(\d+\.\d+) ", line)
    if match:
        timestamps_by_zoom[zoom.group(1)].append(float(match.group(1)))

# One boundary request can fall into an inclusive one-second window. Nginx's
# configured leaky-bucket rate remains 28 requests/second.
overall_peak = 0
for zoom, timestamps in sorted(timestamps_by_zoom.items()):
    window = collections.deque()
    peak = 0
    for timestamp in sorted(timestamps):
        while window and timestamp - window[0] >= 1.0:
            window.popleft()
        window.append(timestamp)
        peak = max(peak, len(window))
    if peak > 29:
        raise SystemExit(
            f"origin peak exceeded limiter at z={zoom}: {peak} requests/second"
        )
    overall_peak = max(overall_peak, peak)
print(f"origin peak under load: {overall_peak} requests/second")
PY

# The proxy must recover normally after the overflow queue has drained.
recovery_url=$(signed_url '/map/tiles/12/1800/1800.png' "$valid_expires")
[ "$(status_for GET "$recovery_url")" = 200 ] \
    || fail "proxy did not recover after queue overflow"

# An upstream failure normally makes Nginx include the complete proxy_pass URL
# in its error log. The origin listener must suppress that message because the
# URL contains the Yandex API key.
sleep 3
docker stop "$MOCK_CONTAINER" >/dev/null
failure_url=$(signed_url '/map/tiles/12/1900/1900.png' "$valid_expires")
failure_status=$(status_for GET "$failure_url")
case "$failure_status" in
    502 | 504) ;;
    *) fail "stopped origin returned unexpected HTTP $failure_status" ;;
esac

proxy_logs=$(docker logs "$PROXY_CONTAINER" 2>&1)
printf '%s' "$proxy_logs" | grep -q "$TEST_API_KEY" \
    && fail "API key leaked into proxy logs"
printf '%s' "$proxy_logs" | grep -q 'signature=' \
    && fail "signed permission leaked into proxy logs"

echo "map-proxy tests passed"
