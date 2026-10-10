# SPDX-License-Identifier: Apache-2.0
ARG BASE=python:3.12-alpine
FROM ${BASE}
RUN apk upgrade --no-cache zlib
RUN pip install --no-cache-dir pytest==9.0.3 && python -m pip uninstall -y pip
WORKDIR /app
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/rhyven-ai/apps"
COPY LICENSE NOTICE main.py pytest_worker.py rhyven_service.py /app/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/app/main.py"]
