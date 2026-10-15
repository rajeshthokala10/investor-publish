# Bengaluru Property Review / Bangalore Realestate Delta - website (FastAPI) for Railway.
# The research batch runs on the publishing machine; it commits refreshed content (data/app, reports)
# and pushes, which redeploys this image with the new content.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
COPY harness/ harness/
COPY analysis/ analysis/
COPY validation/ validation/
COPY noise_removal/ noise_removal/
COPY recheck/ recheck/
COPY content_engineering/ content_engineering/
COPY config/ config/
COPY prompts/ prompts/
COPY data/app/ data/app/
COPY reports/ reports/
RUN useradd --create-home --uid 10001 web && mkdir -p /data && chown -R web /data
EXPOSE 8080
# starts as root only to chown the mounted volume, then drops to 'web' before serving (app/entrypoint.py)
CMD ["python", "-m", "app.entrypoint"]
