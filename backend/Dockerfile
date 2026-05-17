FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir hatch

COPY pyproject.toml .
RUN hatch dep show requirements > requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
