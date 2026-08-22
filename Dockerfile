# Multi-stage: build the React frontend, then run the FastAPI backend that
# serves both the API and the built static files. Suitable for a free
# Hugging Face Docker Space (expects the app on port 7860) or Render/Railway.

# ---- stage 1: frontend build ----
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
# vite.config.js sets outDir to ../backend/app/static, i.e. /backend/app/static
# in this stage (vite creates it). We copy that dir into the backend below.
RUN npm run build

# ---- stage 2: backend ----
FROM python:3.11-slim
WORKDIR /app

# system deps for pdfplumber (needs libjpeg etc. are pulled by wheels; poppler
# optional as pdftotext fallback)
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
# bring in the built frontend
COPY --from=frontend /backend/app/static ./app/static

ENV PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
