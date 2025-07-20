# Use official Python slim image
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y tesseract-ocr libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Expose port
EXPOSE 5000

# Run the app
CMD ["python", "slack_webhook.py"]
