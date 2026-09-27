# SPDX-FileCopyrightText: 2026 Rhyven contributors
# SPDX-License-Identifier: Apache-2.0
FROM python:3.12-alpine
WORKDIR /app
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/rhyven-ai/apps"
COPY LICENSE NOTICE /app/
COPY main.py /app/main.py
ENTRYPOINT ["python", "-B", "/app/main.py"]
