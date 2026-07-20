# Nxcleus control-plane image. Build on the DO VM (native amd64) — this Mac is arm64/colima with no
# buildx (addendum). Runs zero LLM inference; it is the receptionist, not the brain (01 §2).
FROM docker:27.5.1-cli AS docker-cli

FROM python:3.12-slim

# The daemon stays on the VM; the API needs only this pinned client for the mounted host socket.
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1

RUN pip install --no-cache-dir uv

# System deps: tesseract-ocr is the binary behind pytesseract (document intake OCR, boundary stage).
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
# Kept in sync with pyproject.toml [project.dependencies]. pillow/pypdf/pytesseract added for the
# document-intake OCR path (backend Wave 2); tesseract-ocr system binary installed above.
RUN uv pip install --system \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" "sqlalchemy>=2.0" "greenlet>=3.0" "aiosqlite>=0.20" \
    "pydantic>=2.9" "pydantic-settings>=2.6" "httpx>=0.27" "anthropic>=0.40" "python-ulid>=3.0" \
    "pyyaml>=6.0" "cryptography>=43.0" "python-multipart>=0.0.12" "jsonschema>=4.23" \
    "pillow>=12.3.0" "pypdf>=6.14.2" "pytesseract>=0.3.13"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
