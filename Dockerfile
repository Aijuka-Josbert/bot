FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# build tools (needed by cryptography / cffi wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# install dependencies first (better layer caching)
COPY pyproject.toml README.md ./
RUN pip install --upgrade pip

# copy source
COPY bot/ ./bot/
COPY lab/ ./lab/
COPY scripts/ ./scripts/
COPY labs/ ./labs/

# install the package (not editable — source is inside the image)
RUN pip install .

# non-root user
RUN useradd -m -u 1000 botuser \
    && mkdir -p /app/data /app/runtime \
    && chown -R botuser:botuser /app
USER botuser

# defaults: paper mode, forever
ENTRYPOINT ["bot-run"]
CMD ["--ticks", "0", "--poll", "60"]