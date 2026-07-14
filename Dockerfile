FROM python:3.12-slim

WORKDIR /finquery

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY agent/ agent/
COPY baseline/ baseline/
COPY retrieval/ retrieval/
COPY pii/ pii/
COPY guardrails/ guardrails/
COPY ingest/ ingest/
COPY ui/ ui/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
