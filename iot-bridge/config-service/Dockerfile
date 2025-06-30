FROM python:3.9-slim

WORKDIR /app

# Install system dependencies (for Docker CLI access)
RUN apt-get update && apt-get install -y \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY config_sender.py .
COPY static/ ./static/
COPY parser/ ./parser/   

# ✅ NON CREARE DIRECTORY templates - lascia che i mount le gestiscano

EXPOSE 8080

CMD ["python", "config_sender.py"]
