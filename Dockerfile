
FROM python:3.11-slim

WORKDIR /app

COPY backend /app/backend
COPY frontend /app/frontend
COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
