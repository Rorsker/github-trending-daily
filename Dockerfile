FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    TRENDING_OUTPUT_ROOT=/data/output \
    CODEX_HOME=/run/codex

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm tzdata ca-certificates \
    && npm install -g @openai/codex@0.163.0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /root/.npm

WORKDIR /app
COPY trending.py analysis.schema.json daily.py ./
COPY feishu/feishu_notifier.py feishu/send_report.py ./feishu/
COPY deploy/container-entrypoint.sh ./deploy/
RUN chmod 755 ./deploy/container-entrypoint.sh \
    && mkdir -p /data/output /run/codex

VOLUME /data/output
ENTRYPOINT ["/app/deploy/container-entrypoint.sh"]
CMD ["sleep", "infinity"]
