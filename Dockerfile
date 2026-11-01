FROM python:3.11-slim

WORKDIR /app

# Copy application files
COPY . /app

# Port setup
ENV PORT=5000
EXPOSE 5000

# Start trading terminal
CMD ["python", "server.py"]
