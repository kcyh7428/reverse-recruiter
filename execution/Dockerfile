# Use official Playwright Python image (includes Python 3.11, Node.js, and Browsers)
# This avoids the large browser download during build which was failing
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Install system dependencies
# Node.js is NOT present in the python image by default, so we must install it.
# agent-browser is a node package.
# Added --fix-missing to handle potential repo network timeouts
RUN apt-get update --fix-missing && apt-get install -y \
    curl \
    gnupg \
    xvfb \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Vercel Agent Browser CLI and pin Playwright version
# We install agent-browser, then force-downgrade its internal playwright-core dependency
# to 1.49.0 to match the browser binaries pre-installed in this Docker image.
RUN npm install -g agent-browser \
    && cd "$(npm root -g)/agent-browser" \
    && npm install playwright-core@1.49.0

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
# 1 worker, 8 threads to handle concurrent requests
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 900 main:app
