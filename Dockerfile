FROM python:3.13-slim
WORKDIR /app
COPY requirements-taskflow.txt .
RUN pip install --no-cache-dir -r requirements-taskflow.txt
COPY taskflow/ ./taskflow/
CMD ["uvicorn", "taskflow.main:app", "--host", "0.0.0.0", "--port", "8000"]
