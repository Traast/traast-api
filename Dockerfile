FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "echo '[debug] DATABASE_URL set:' && env | grep -c DATABASE_URL && echo '[debug] All env var names:' && env | cut -d= -f1 | sort && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
