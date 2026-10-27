FROM node:22-bookworm-slim AS frontend-build

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend-build /frontend/dist ./frontend/dist

ENV PYTHONPATH=/app/backend
ENV HOST=0.0.0.0
ENV FLASK_ENV=production
EXPOSE 10000
CMD ["python", "backend/main.py"]
