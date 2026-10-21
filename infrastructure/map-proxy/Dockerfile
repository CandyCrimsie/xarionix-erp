FROM nginx:1.29-alpine

COPY nginx.conf /etc/nginx/nginx.conf
COPY default.conf.template /etc/nginx/templates/default.conf.template
COPY validate-map-env.sh /docker-entrypoint.d/05-validate-map-env.sh

RUN chmod 0755 /docker-entrypoint.d/05-validate-map-env.sh

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
