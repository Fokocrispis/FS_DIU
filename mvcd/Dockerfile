FROM --platform=linux/arm64/v8 python:3.11-slim

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install dependencies for python-can, Tkinter, CAN utilities, and SQLite
RUN apt-get update && apt-get install -y \
    python3-dev \
    build-essential \
    tk \
    libtk8.6 \
    libtcl8.6 \
    iproute2 \
    can-utils \
    x11-utils \
    sqlite3 \
    libsqlite3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency list and install pip packages
COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Create non-root user
RUN adduser --disabled-password --gecos "" --uid 5678 appuser \
    && chown -R appuser /app
USER appuser

# Copy application code
COPY . /app

# Run the application
CMD ["python", "main.py"]
