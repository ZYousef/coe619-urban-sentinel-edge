#!/usr/bin/env python3

import csv
import random
import os
import sys

# Define paths
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))  # /app
CSV_FILE = os.path.join(os.path.dirname(__file__), "valid_english_named_random_points_riyadh.csv")
ENV_FILE = os.path.join(APP_DIR, ".env")

def pick_valid_point():
    """Selects a valid location (name, lat, lon) from the CSV file."""
    try:
        with open(CSV_FILE, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            points = [
                (row[2].strip(), float(row[1][7:-1].split()[1]), float(row[1][7:-1].split()[0]))
                for row in reader if len(row) >= 3 and row[2].strip() and len(row[2].strip()) > 6
                and row[1].startswith("POINT (") and row[1].endswith(")")
            ] #pick sensible names.
        return random.choice(points) if points else sys.exit("Error: No valid points found.")
    except FileNotFoundError:
        sys.exit(f"Error: CSV file not found at {CSV_FILE}")
    except Exception as e:
        sys.exit(f"Unexpected error: {e}")

def save_env(env_vars):
    """Saves environment variables to a .env file."""
    try:
        with open(ENV_FILE, "w") as f:
            f.writelines(f"{k}={v}\n" for k, v in env_vars.items())
        print(f"✅ Saved environment variables to {ENV_FILE}")
    except Exception as e:
        sys.exit(f"Error writing .env file: {e}")

def main():
    name, lat, lon = pick_valid_point()
    save_env({"NODE_NAME": name, "NODE_LATITUDE": lat, "NODE_LONGITUDE": lon})

if __name__ == "__main__":
    main()
