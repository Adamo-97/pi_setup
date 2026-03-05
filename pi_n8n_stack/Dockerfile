# ============================================================================
# Custom n8n image — multi-stage build to add Python 3 to the hardened
# n8n image (apk is stripped in Docker Hardened Images, so we copy
# Python + packages from a standard Alpine build stage instead).
# ============================================================================

# Stage 1: install Python packages into a prefix directory
FROM python:3.11-alpine3.22 AS python-builder

COPY pi_n8n_stack/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --prefix=/python-dist \
    -r /tmp/requirements.txt

# Stage 2: final n8n image with Python injected
FROM n8nio/n8n:latest

USER root

# Copy the Python interpreter and stdlib from the builder
COPY --from=python-builder /usr/local/bin/python3.11 /usr/local/bin/python3.11
COPY --from=python-builder /usr/local/bin/python3   /usr/local/bin/python3
COPY --from=python-builder /usr/local/lib/python3.11 /usr/local/lib/python3.11

# Copy the installed packages into the same prefix
COPY --from=python-builder /python-dist /usr/local

# Symlink for bare 'python' calls
RUN ln -sf /usr/local/bin/python3.11 /usr/local/bin/python

USER node
