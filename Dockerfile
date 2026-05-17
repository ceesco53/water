# Stage 1: Build React frontend
FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Python backend + serve static React build
FROM python:3.11-slim
WORKDIR /app

RUN pip install --no-cache-dir hatch

COPY backend/pyproject.toml ./pyproject.toml
RUN hatch dep show requirements > requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend-build /frontend/dist ./static

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
