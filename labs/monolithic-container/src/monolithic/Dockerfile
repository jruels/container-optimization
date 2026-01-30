# Monolithic Container - Anti-pattern demonstration
# This container runs multiple services: Redis + Python Web App + Process Manager

FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install ALL dependencies in a single layer (bad practice for demonstration)
RUN apt-get update && apt-get install -y \
    # Python and web dependencies
    python3 \
    python3-pip \
    python3-dev \
    # Redis server
    redis-server \
    # Process manager to run multiple services
    supervisor \
    # Debugging tools (often included unnecessarily)
    curl \
    wget \
    vim \
    htop \
    net-tools \
    iputils-ping \
    # Build tools (not needed at runtime)
    build-essential \
    gcc \
    # Clean up (but damage is done - layer is already large)
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip3 install --no-cache-dir \
    flask==3.0.0 \
    redis==5.0.1 \
    gunicorn==21.2.0 \
    requests==2.31.0

# Create application directory
WORKDIR /app

# Copy application code
COPY app.py /app/

# Create supervisord configuration to manage multiple processes
RUN mkdir -p /var/log/supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose the web application port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Run supervisord to manage all processes
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
