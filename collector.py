# Hyperliquid Data Collector (collector.py)
#
# This script runs in the background to fetch the price of a specified coin
# every minute and save it to a JSON file.
#
# It includes exponential backoff to handle API rate limiting (429 errors) gracefully.
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
    
    # --- NEW: Variables for exponential backoff ---
    backoff_time = FETCH_INTERVAL_SECONDS # Start with the default interval

    try:
        while True:
            try:
                # Fetch the latest mid-price
                all_mids = info.all_mids()
                
                # --- NEW: Reset backoff time on a successful request ---
                backoff_time = FETCH_INTERVAL_SECONDS
                
                if COIN_TO_TRACK in all_mids:
                    price = float(all_mids[COIN_TO_TRACK])
                    timestamp = datetime.now().isoformat()

                    new_entry = {"timestamp": timestamp, "price": price}
                    price_history.append(new_entry)

                    save_data(price_history)

                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved: {COIN_TO_TRACK} @ ${price:.2f}")

                else:
                    print(f"[!] Error: Coin '{COIN_TO_TRACK}' not found.")

            # --- NEW: Catch the specific rate limit error ---
            except Exception as e:
                # Check if the error is a rate limit error (HTTP 429)
                if '429' in str(e):
                    print(f"\n[!] Rate limit exceeded (429). Backing off for {backoff_time} seconds...")
                    time.sleep(backoff_time)
                    # Double the backoff time for the next potential failure
                    backoff_time *= 2 
                    continue # Skip the rest of the loop and try again
                else:
                    # Handle other errors
                    print(f"\n[!] An unexpected error occurred: {e}")
            
            # Wait for the normal interval before the next fetch
            time.sleep(FETCH_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n[*] Data collection stopped.")

if __name__ == "__main__":
    collect_data()
