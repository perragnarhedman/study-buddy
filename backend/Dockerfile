FROM python:3.11-slim

WORKDIR /app

# System deps (minimal; keep image small)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app

EXPOSE 8000

# NOTE: configure with env vars (OPENAI_API_KEY, SESSION_SECRET, SQLITE_PATH, etc.)
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


