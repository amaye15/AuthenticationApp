# # Use an official Python runtime as a parent image
# FROM python:3.12-slim

# WORKDIR /code

# COPY ./requirements.txt /code/requirements.txt

# RUN pip install --no-cache-dir --upgrade pip && \
#     pip install --no-cache-dir -r requirements.txt

# # Copy application code
# COPY ./app /code/app
# # Copy static files and templates
# COPY ./static /code/static
# COPY ./templates /code/templates

# EXPOSE 7860

# # Command to run the FastAPI application
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]

# Use an official Python runtime as a parent image
FROM python:3.12-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONOPTIMIZE=2

WORKDIR /build

# Copy only requirements first to leverage Docker caching
COPY ./requirements.txt .

# Install dependencies into a virtual environment
RUN python -m venv /venv && \
    /venv/bin/pip install --no-cache-dir --upgrade pip && \
    /venv/bin/pip install --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONOPTIMIZE=2 \
    PATH="/venv/bin:$PATH"

WORKDIR /app

# Create a non-root user
RUN addgroup --system app && \
    adduser --system --group app && \
    chown -R app:app /app

# Copy the virtual environment from the builder stage
COPY --from=builder /venv /venv

# Copy application code and assets
COPY --chown=app:app ./app ./app
COPY --chown=app:app ./static ./static
COPY --chown=app:app ./templates ./templates

# Expose the port
EXPOSE 7860

# Switch to non-root user
USER app

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

# Command to run the FastAPI application with optimized settings
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "4", "--proxy-headers"]