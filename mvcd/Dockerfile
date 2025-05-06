# Explicitly use arm64 architecture for Raspberry Pi 5
FROM --platform=linux/arm64/v8 python:3.11-slim-bookworm

# Set labels for better maintainability
LABEL maintainer="Formula Student Team"
LABEL version="1.0"
LABEL description="Formula Student Car Display Dashboard"

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Europe/Berlin \
    PIP_NO_CACHE_DIR=1

# Set working directory
WORKDIR /app

# Install dependencies for python-can, Tkinter, CAN utilities - all in one layer to reduce image size
RUN apt-get update && apt-get install -y --no-install-recommends \
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

# Copy only requirements.txt first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash --uid 1000 appuser \
    && chown -R appuser:appuser /app

# Copy application code
COPY . /app
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Allow X11 forwarding for GUI
ENV DISPLAY=:0

# Create config directory
RUN mkdir -p /app/config

# Set entrypoint that checks for virtual CAN setup and falls back when needed
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]

# Run the application
CMD ["python", "main.py", "--debug"]