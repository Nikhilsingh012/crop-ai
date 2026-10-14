FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONPATH=/app/backend
ENV HOST=0.0.0.0
EXPOSE 5000
CMD ["python", "backend/main.py"]
