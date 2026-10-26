FROM node:20-slim AS codex
RUN npm install -g @openai/codex@0.163.0

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    TRENDING_OUTPUT_ROOT=/data/output \
    CODEX_HOME=/run/codex

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=codex /usr/local/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/ /opt/codex/
RUN ln -s /opt/codex/bin/codex /usr/local/bin/codex

WORKDIR /app
COPY trending.py analysis.schema.json daily.py ./
COPY feishu/feishu_notifier.py feishu/send_report.py ./feishu/
COPY deploy/container-entrypoint.sh ./deploy/
RUN chmod 755 ./deploy/container-entrypoint.sh \
    && mkdir -p /data/output /run/codex

VOLUME /data/output
ENTRYPOINT ["/app/deploy/container-entrypoint.sh"]
CMD ["sleep", "infinity"]
