FROM python:3.11-slim

WORKDIR /app

# Copy application files
COPY . /app

# Port setup (Hugging Face Spaces uses 7860 by default)
ENV PORT=7860
EXPOSE 7860

# Start trading terminal
CMD ["python", "server.py"]
