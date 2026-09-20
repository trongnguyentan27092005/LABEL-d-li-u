FROM python:3.11-slim

WORKDIR /app
COPY app.py /app/app.py

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8765

# The data directory is intentionally not in Git. Mount it as a private volume
# at /app/Data when deploying an annotation service.
EXPOSE 8765
CMD ["sh", "-c", "python /app/app.py --input /app/input.csv --subset ${SUBSET:-core-1000} --host 0.0.0.0 --port ${PORT}"]
