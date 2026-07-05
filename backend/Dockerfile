# Stage 1: Build stage
FROM python:3.13-slim AS builder

WORKDIR /build

# Install build dependencies (required for compiling psycopg2 and other wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Generate wheels and install to user space
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Slim runtime stage
FROM python:3.13-slim AS runner

WORKDIR /app

# Install runtime database clients (libpq5 is needed for postgres runtime link)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy the dependencies from builder
COPY --from=builder /root/.local /root/.local

# Copy the application source code
COPY . .

# Update path to resolve installed commands (like uvicorn, alembic)
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Start server using uvicorn
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
