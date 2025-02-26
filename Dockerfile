# Use official Python image
FROM python:3.9

# Set working directory
WORKDIR /app

# Copy files
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port (for Koyeb)
EXPOSE 8080

# Start bot
CMD ["python", "zip_bot.py"]
