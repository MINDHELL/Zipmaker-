FROM python:3.11-slim

WORKDIR /app

# System tools required for zip/rejoin/rar
RUN apt-get update && apt-get install -y \
    p7zip-full \
    unrar \
    zip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
