# Use official Python slim image as base
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (including ffmpeg for pydub)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements.txt and install Python dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy project files
COPY . /app/

# Collect static files (إذا انت بتستخدم static files في مشروعك)
RUN python manage.py collectstatic --noinput

# Expose the port that gunicorn will run on
EXPOSE 8000

# Run migrations (لو حابب تعمل migrate تلقائي عند بداية الكونتينر)
# RUN python manage.py migrate

# Command to run the app using gunicorn
CMD ["gunicorn", "iGPT.wsgi:application", "--bind", "0.0.0.0:8000"]
