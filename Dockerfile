FROM python:3.11-slim

WORKDIR /app

COPY . /app

ENV PYTHONUNBUFFERED=1
ENV PORT=7860

EXPOSE 7860

CMD ["python", "server.py"]
