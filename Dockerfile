# Use a lightweight base image with Python 3.11
FROM python:3.11-slim

# Prevents prompts during install
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies for OCR + image handling
RUN apt update && apt install -y \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (if needed)
EXPOSE 5000

# Start the Flask app
CMD ["python3", "slack_webhook.py"]
