# Use the official Python image.
FROM python:3.11-slim

# Set environment variables.
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory.
WORKDIR /app

# Install dependencies.
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy project.
COPY . /app

# Expose port
EXPOSE 6000

# Run Gunicorn server.
CMD ["gunicorn", "--bind", "0.0.0.0:6000", "app:app"]
