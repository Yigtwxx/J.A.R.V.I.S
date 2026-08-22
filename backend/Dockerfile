# Pin the Debian release, not just the Python version: the floating `-slim` tag
# moved from bookworm to trixie and silently broke the apt packages below.
FROM python:3.11-slim-trixie AS runtime

WORKDIR /app

# System libraries required by deepface's OpenCV backend.
# On trixie libgl1-mesa-glx was folded into libgl1, and libglib2.0-0 was
# renamed libglib2.0-0t64 by the 64-bit time_t transition.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0t64 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data directory for SQLite
RUN mkdir -p data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# ---------------------------------------------------------------------------
# runtime-stealth — the same service, plus a browser.
#
# The `runtime` stage above has no browser, so the discovery pipeline's stealth
# tier cannot start there: `FetchSession` reports `stealth_unavailable` and every
# platform that needs a browser comes back `blocked`. That degradation is by
# design and it is silent, which is precisely why it went unnoticed in compose.
#
# It is a separate target rather than the default because the browser and its
# runtime libraries add several hundred MB, and a deployment that only needs the
# HTTP tier should not pay for that. docker-compose.yml builds this target.
# ---------------------------------------------------------------------------
FROM runtime AS runtime-stealth

# Chromium's runtime dependencies. Playwright's own `install-deps` would pull a
# broader set; this is the list Chromium actually links against, kept explicit so
# a base-image change fails loudly at build time instead of at the first fetch.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0t64 libatk-bridge2.0-0t64 \
    libcups2t64 libdrm2 libxkbcommon0 libatspi2.0-0t64 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 \
    libasound2t64 fonts-liberation fonts-unifont \
    && rm -rf /var/lib/apt/lists/*

# Keep the browser inside the image rather than in a per-user cache, so it is
# present for whatever UID the container ends up running as.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
RUN scrapling install

# No real Chrome exists in this image; the launcher falls back to the bundled
# Chromium on its own, but saying so here avoids a pointless first attempt.
ENV DISCOVERY_REAL_CHROME=false

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
