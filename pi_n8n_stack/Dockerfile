# ============================================================================
# Custom n8n image — multi-stage build to add Python 3 to the hardened
# n8n image (apk is stripped in Docker Hardened Images, so we copy
# the full Python install + shared libs from a standard Alpine stage).
# ============================================================================

# Stage 1: install Python + pip packages on standard Alpine
FROM python:3.11-alpine3.22 AS python-builder

COPY pi_n8n_stack/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Collect all shared libraries Python depends on (libffi, libssl, etc.)
RUN mkdir -p /python-libs && \
    for lib in $(ldd /usr/local/bin/python3.11 2>/dev/null | awk '/=>/{print $3}'); do \
    cp -L "$lib" /python-libs/ 2>/dev/null || true; \
    done

# Create yt-dlp CLI wrapper (pip entry point scripts aren't preserved in multi-stage copy)
RUN printf '#!/usr/local/bin/python3.11\nimport sys; from yt_dlp import main; main()\n' \
    > /usr/local/bin/yt-dlp && chmod +x /usr/local/bin/yt-dlp

# Stage 1b: grab statically-linked ffmpeg + ffprobe (no shared-lib headaches)
FROM mwader/static-ffmpeg:7.1.1 AS ffmpeg-builder

# Stage 2: final n8n image with Python injected
FROM n8nio/n8n:latest

USER root

# Copy Python interpreter, stdlib, and all pip-installed packages
COPY --from=python-builder /usr/local/bin/python3*  /usr/local/bin/
COPY --from=python-builder /usr/local/bin/yt-dlp     /usr/local/bin/yt-dlp
COPY --from=python-builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=python-builder /usr/local/lib/libpython3* /usr/local/lib/

# Copy shared libraries that Python links against
COPY --from=python-builder /python-libs/ /usr/lib/

# Copy ffmpeg + ffprobe (statically linked — no shared libs needed)
COPY --from=ffmpeg-builder /ffmpeg /usr/local/bin/ffmpeg
COPY --from=ffmpeg-builder /ffprobe /usr/local/bin/ffprobe

# Symlink for bare 'python' calls and update library cache
RUN ln -sf /usr/local/bin/python3.11 /usr/local/bin/python && \
    ldconfig /usr/local/lib /usr/lib 2>/dev/null || true

USER node
