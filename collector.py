# Hyperliquid Data Collector (collector.py)
#
# This script runs in the background to fetch the price of a specified coin
# every minute and save it to a JSON file.
#
# To Run:
# 1. Save this file as 'collector.py'.
# 2. Run from your terminal: python collector.py
# 3. Leave it running. It will create and update 'price_data.json' in the same directory.

import time
import json
from datetime import datetime
from hyperliquid.info import Info
import os

# --- Configuration ---
COIN_TO_TRACK = "SOL"
DATA_FILE = "price_data.json"
FETCH_INTERVAL_SECONDS = 60 # Fetch data every 60 seconds (1 minute)

def load_data():
    """Loads existing price data from the JSON file."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return [] # Return empty list if file is empty or corrupted
    return []

def save_data(data):
    """Saves the updated price data to the JSON file."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def collect_data():
    """
    The main function to collect and save price data periodically.
    """
    print("--- Data Collector Service ---")
    print(f"[*] Collecting 1-minute data for: {COIN_TO_TRACK}")
    print(f"[*] Saving data to: {DATA_FILE}")
    print("[*] Press CTRL+C to stop.")
    print("-" * 30)

    info = Info()
    price_history = load_data()

    try:
        while True:
            # Fetch the latest mid-price
            all_mids = info.all_mids()
            if COIN_TO_TRACK in all_mids:
                price = float(all_mids[COIN_TO_TRACK])
                timestamp = datetime.now().isoformat()

                # Create new data point
                new_entry = {"timestamp": timestamp, "price": price}
                price_history.append(new_entry)

                # Save the updated list back to the file
                save_data(price_history)

                print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved: {COIN_TO_TRACK} @ ${price:.2f}")

            else:
                print(f"[!] Error: Coin '{COIN_TO_TRACK}' not found.")

            # Wait for the specified interval
            time.sleep(FETCH_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n[*] Data collection stopped.")
    except Exception as e:
        print(f"\n[!] An error occurred: {e}")

if __name__ == "__main__":
    collect_data()
