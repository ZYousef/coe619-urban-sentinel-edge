#!/usr/bin/env python3

import csv
import random
import sys

CSV_FILE = "valid_english_named_random_points_riyadh.csv"

def pick_valid_point(csv_file):
    """Return one (name, lat, lon) from the CSV with place name > 6 chars."""
    points = []
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            # Expect [ID, POINT (lon lat), PlaceName]
            if len(row) < 3:
                continue
            point_str = row[1].strip()
            if not (point_str.startswith("POINT (") and point_str.endswith(")")):
                continue
            coords = point_str[7:-1].split()
            if len(coords) != 2:
                continue
            try:
                lon = float(coords[0])
                lat = float(coords[1])
            except ValueError:
                continue
            name = row[2].strip()
            if len(name) > 6:
                points.append((name, lat, lon))
    if not points:
        raise ValueError("No valid points found in CSV with place name length > 6.")
    return random.choice(points)

def main():
    try:
        name, lat, lon = pick_valid_point(CSV_FILE)
        env_vars = {
            "NODE_NAME": name,
            "LATITUDE": str(lat),
            "LONGITUDE": str(lon),
        }
        # Output environment variables in VAR=VALUE format
        for var, val in env_vars.items():
            val_escaped = val.replace('"', '\\"')
            print(f'export {var}="{val_escaped}"')
    except Exception as e:
        print("Error:", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
