# Continuity Room — single Cloud Run service serving the FastAPI backend
# (which orchestrates the three ADK agents) and the built React frontend as
# static files from the same container.

FROM node:20-alpine AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS backend
WORKDIR /app/backend

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist

ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT}"]
