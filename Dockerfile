# One image: the React build is served by Django (WhiteNoise) next to the API.

FROM node:22-alpine AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_DEBUG=false \
    PORT=8000
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /app/frontend/dist /app/frontend/dist
EXPOSE 8000
# One worker with threads so every request shares the in-memory forecast cache.
# `exec` makes gunicorn PID 1 so it receives the platform's stop signal.
CMD ["sh", "-c", "exec gunicorn config.wsgi --bind 0.0.0.0:${PORT} --workers 1 --threads 8 --timeout 90"]
