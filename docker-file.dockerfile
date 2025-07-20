FROM python:3.11-slim

# Install Tesseract & dependencies
RUN apt-get update && \
    apt-get install -y tesseract-ocr libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "slack_webhook.py"]
