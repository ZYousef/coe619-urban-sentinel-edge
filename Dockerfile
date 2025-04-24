# Use the slim Python base…
FROM python:3.11-slim

# 1) Install OS packages required to compile C/C++ Python extensions
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      gcc \
      g++ \
      python3-dev \
      libatlas-base-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2) Copy and install Python requirements
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 3) Copy the rest of your application
COPY . .

# 4) Clean up
RUN rm -f requirements.txt \
    && touch .env

# 5) Entrypoint: run your helper script
CMD ["python3", "./helpers/run_scripts.py"]