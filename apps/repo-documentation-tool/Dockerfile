# SPDX-FileCopyrightText: 2026 Rhyven contributors
# SPDX-License-Identifier: Apache-2.0
FROM node:22-bookworm-slim AS node
WORKDIR /opt/ls
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --omit=dev

FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    python3 python3-venv clangd gopls golang-go rustc cargo rust-src \
    openjdk-21-jre-headless ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* /usr/src/rustc-*/src/ci
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /opt/ls /opt/ls
RUN python3 -m venv /opt/fortls && /opt/fortls/bin/pip install --no-cache-dir fortls==3.2.2 \
    && /opt/fortls/bin/python -m pip uninstall -y pip \
    && apt-get purge -y python3-venv python3.12-venv python3-pip-whl python3-setuptools-whl
COPY toolchains.json install_toolchains.py /build/
RUN python3 /build/install_toolchains.py && ln -s /opt/jdtls/bin/jdtls /usr/local/bin/jdtls
ENV PATH="/opt/ls/node_modules/.bin:/opt/fortls/bin:/usr/local/bin:/usr/bin:/bin" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/rhyven-ai/apps"
COPY LICENSE NOTICE /app/
COPY atlas.py lsp.py main.py ./
ENTRYPOINT ["python3", "/app/main.py"]
