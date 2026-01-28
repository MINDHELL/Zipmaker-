FROM python:3.11-slim

WORKDIR /app

# Prevent interactive issues
ENV DEBIAN_FRONTEND=noninteractive

# Install system tools
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        p7zip-full \
        unrar-free \
        zip \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
