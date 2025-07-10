FROM python:3.13-slim

# Set environment variables
ENV POETRY_VERSION=1.8.2 \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONUNBUFFERED=1

# Install Poetry and system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-deu \
    libsane \
    sane-utils && \
    pip install "poetry==$POETRY_VERSION" && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY pyproject.toml poetry.lock ./
COPY src ./src

# Install dependencies
RUN poetry install --no-interaction --no-ansi

EXPOSE 7500

# Run the app
CMD ["python", "src/main.py"]
