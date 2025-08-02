# Hyperliquid Real-Time Price Tracker
#
# This script continuously fetches and displays the mid-price of a specified 
# cryptocurrency from the Hyperliquid exchange every second.
#
# To use this script:
# 1. Make sure you have the Hyperliquid Python SDK installed:
#    pip install hyperliquid-python-sdk
#
# 2. Change the 'COIN_TO_TRACK' variable to the asset you want to monitor (e.g., "BTC", "ETH", "SOL").
#
# 3. Run the script from your terminal:
#    python your_script_name.py
#
# 4. Press CTRL+C to stop the tracker.

import time
from datetime import datetime
from hyperliquid.info import Info

# --- Configuration ---
# Change this to the coin you want to track (e.g., "BTC", "ETH", "PURR")
COIN_TO_TRACK = "SOL" 

def track_price():
    """
    Fetches and prints the price of a specified coin every second.
    """
    print("--- Hyperliquid Price Tracker ---")
    print(f"[*] Tracking price for: {COIN_TO_TRACK}")
    print("[*] Press CTRL+C to stop.")
    print("-" * 33)

    try:
        # Initialize the Info object outside the loop for efficiency
        info = Info()
        
        # The main loop to fetch the price continuously
        while True:
            # Fetch the mid-prices for all available assets
            all_mids = info.all_mids()

            # Check if the coin we are tracking exists in the response
            if COIN_TO_TRACK in all_mids:
                # Get the price and the current timestamp
                price = float(all_mids[COIN_TO_TRACK])
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # Print the formatted price data
                # The '\r' at the beginning moves the cursor to the start of the line,
                # effectively overwriting the previous line for a clean, single-line display.
                print(f"\r[{timestamp}] {COIN_TO_TRACK} Price: ${price:<10.4f}", end="", flush=True)

            else:
                print(f"\n[!] Error: Coin '{COIN_TO_TRACK}' not found in the API response.")
                break # Exit the loop if the coin is not found

            # Wait for 1 second before the next fetch
            time.sleep(1)

    except KeyboardInterrupt:
        # Handle the user pressing CTRL+C to exit gracefully
        print("\n\n[*] Price tracker stopped. Goodbye!")
    except Exception as e:
        # Handle any other potential errors (e.g., network issues)
        print(f"\n[!] An error occurred: {e}")

if __name__ == "__main__":
    track_price()