# FTM Language Generator: the React page (language_automation/web, spec 012), its Python server
# (server.py) and the pipeline scripts, for Cloud Run. Built by cloudbuild.yaml. Secrets are never
# baked in: .dockerignore keeps them out, and Cloud Run takes them from Secret Manager at run time:
# the web OAuth client as a file, the Gemini key as the env var GEMINI_API_KEY.

# 1) Build the page (type check + Vite). Node stays in this stage only.
FROM node:22-slim AS web
WORKDIR /web
COPY language_automation/web/package.json language_automation/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY language_automation/web/ ./
RUN npm run build

# 2) The server and the pipeline
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ffmpeg converts non-mp3 audio (fetch_drive_audios.py)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY language_automation/ ./language_automation/
RUN rm -rf ./language_automation/web
COPY --from=web /web/dist ./language_automation/web/dist

# Run as a non-root user that can write lang/ and .ai_cache/ next to the scripts
RUN useradd --create-home --uid 10001 ftm \
    && chown -R ftm:ftm /app/language_automation
USER ftm

# The scripts read their files relative to this folder
WORKDIR /app/language_automation

# Cloud Run sets PORT. FTM_HOSTED / FTM_OAUTH_CLIENT_FILE are set by the deploy (cloudbuild.yaml),
# not here, so the image can also be run locally (docker run -p 8080:8080 ...).
ENV PORT=8080 HOST=0.0.0.0
EXPOSE 8080
CMD ["python", "server.py"]
