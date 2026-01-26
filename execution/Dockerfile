# Use a full Python runtime to ensure all build tools are present
FROM python:3.11

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Install system dependencies
# We need Node.js for Vercel Agent Browser, and Chromium for the browser engine
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    unzip \
    xvfb \
    chromium \
    chromium-driver \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Vercel Agent Browser CLI
# Installing globally to make 'agent-browser' command available
RUN npm install -g agent-browser

# Set work directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the port
EXPOSE 8080

# Use Gunicorn as the production server
# 1 worker, 8 threads to handle concurrent requests (Cloud Run scales containers)
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
