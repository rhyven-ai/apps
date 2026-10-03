# SPDX-FileCopyrightText: 2026 Rhyven contributors
# SPDX-License-Identifier: Apache-2.0
ARG BASE=python:3.12-alpine
FROM ${BASE}
# This service has no third-party Python dependencies. Do not ship an unused installer.
RUN python -m pip uninstall -y pip
WORKDIR /app
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/rhyven-ai/rhyven"
COPY LICENSE NOTICE /app/
COPY main.py rhyven_service.py /app/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/app/main.py"]
