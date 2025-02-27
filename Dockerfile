# Use Python base image
FROM python:3.9

# Set working directory
WORKDIR /app

# Copy all files
COPY . .

# Install dependencies
RUN pip install -r requirements.txt

# Expose port 8000 for health checks
EXPOSE 8000

# Run bot and health check server in parallel
CMD python zip_bot.py & python server.py
