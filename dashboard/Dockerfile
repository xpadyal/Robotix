# dashboard/Dockerfile

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy static files first to catch any issues early
COPY static/ /app/static/

# Copy the rest of the application
COPY main.py .
COPY *.py ./

EXPOSE 8080

# Make sure the static directory exists (create if not copied)
RUN mkdir -p /app/static

CMD ["python", "main.py"]
