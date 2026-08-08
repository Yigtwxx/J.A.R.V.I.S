# Pin the Debian release, not just the Python version: the floating `-slim` tag
# moved from bookworm to trixie and silently broke the apt packages below.
FROM python:3.11-slim-trixie

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
