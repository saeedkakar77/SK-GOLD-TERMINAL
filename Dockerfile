FROM python:3.11-slim

WORKDIR /app

COPY . /app

ENV PYTHONUNBUFFERED=1
ENV RENDER=true

EXPOSE 5000

CMD ["python", "-u", "server.py"]
