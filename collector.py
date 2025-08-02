# Hyperliquid Data Collector (collector.py)
#
# This script runs in the background to fetch the price of specified coins
# every minute and save each to a separate JSON file.
#
# It includes exponential backoff to handle API rate limiting (429 errors) gracefully.
#
# To Run:
# 1. Save this file as 'collector.py'.
# 2. Make sure you have the hyperliquid-python-sdk installed: pip install hyperliquid-python-sdk
# 3. Run from your terminal: python collector.py
# 4. Leave it running. It will create and update the specified JSON files.

import time
import json
import os
from datetime import datetime
from hyperliquid.info import Info

# --- Configuration ---
# List of tuples, where each tuple is (COIN_SYMBOL, FILENAME)
COINS_TO_TRACK = [
    ("SOL", "price_data.json"),
    ("LTC", "ltc_price_data.json")
]
FETCH_INTERVAL_SECONDS = 60  # Fetch data every 60 seconds (1 minute)

def load_data(file_path):
    """Loads existing price data from a specific JSON file."""
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []  # Return empty list if file is empty or corrupted
    return []

def save_data(data, file_path):
    """Saves the updated price data to a specific JSON file."""
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

def collect_data():
    """
    The main function to collect and save price data periodically for multiple coins.
    """
    print("--- Data Collector Service ---")
    tracked_coins = [coin for coin, _ in COINS_TO_TRACK]
    print(f"[*] Collecting 1-minute data for: {', '.join(tracked_coins)}")
    print("[*] Press CTRL+C to stop.")
    print("-" * 30)

    info = Info()
    # Exponential backoff starts at the default fetch interval
    backoff_time = FETCH_INTERVAL_SECONDS

    try:
        while True:
            try:
                # Fetch the latest mid-price for all available markets
                all_mids = info.all_mids()
                
                # On a successful API call, reset the backoff timer
                backoff_time = FETCH_INTERVAL_SECONDS
                
                # Iterate through the list of coins we want to track
                for coin_symbol, data_file in COINS_TO_TRACK:
                    if coin_symbol in all_mids:
                        price = float(all_mids[coin_symbol])
                        timestamp = datetime.now().isoformat()
                        new_entry = {"timestamp": timestamp, "price": price}

                        # Load, update, and save data for this specific coin
                        price_history = load_data(data_file)
                        price_history.append(new_entry)
                        save_data(price_history, data_file)

                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved: {coin_symbol} @ ${price:,.2f} to {data_file}")
                    else:
                        print(f"[!] Error: Coin '{coin_symbol}' not found in the API response.")

            except Exception as e:
                # Check if the error is a rate limit error (HTTP 429)
                if '429' in str(e):
                    print(f"\n[!] Rate limit exceeded (429). Backing off for {backoff_time} seconds...")
                    time.sleep(backoff_time)
                    # Double the backoff time for the next potential failure
                    backoff_time = min(backoff_time * 2, 3600) # Cap backoff at 1 hour
                    continue  # Skip the rest of the loop and try the API call again
                else:
                    # Handle other unexpected errors
                    print(f"\n[!] An unexpected error occurred: {e}")
            
            # Wait for the normal interval before the next fetch cycle
            time.sleep(FETCH_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n[*] Data collection stopped.")

if __name__ == "__main__":
    collect_data()