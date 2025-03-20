# Use an official Python runtime as a parent image
FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt
# Remove requirements.txt after installation
RUN rm -f requirements.txt
# Ensure .env file is always available

RUN touch .env

# Run script on container launch
CMD ["python3", "./helpers/run_scripts.py"]
