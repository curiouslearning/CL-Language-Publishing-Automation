# FTM Language Generator: the Streamlit page (app.py) and the pipeline scripts, for Cloud Run.
# Built by cloudbuild.yaml. Secrets are never baked in: .dockerignore keeps them out, and Cloud Run
# takes them from Secret Manager at run time: the web OAuth client as a file, the Gemini key as the
# env var GEMINI_API_KEY.
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

# Run as a non-root user that can write lang/ and .ai_cache/ next to the scripts
RUN useradd --create-home --uid 10001 ftm \
    && chown -R ftm:ftm /app/language_automation
USER ftm

# The scripts read their files relative to this folder
WORKDIR /app/language_automation

# Cloud Run sets PORT. FTM_HOSTED / FTM_PUBLIC_URL / FTM_OAUTH_CLIENT_FILE are set by the deploy
# (cloudbuild.yaml), not here, so the image can also be run locally.
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "exec python -m streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]
