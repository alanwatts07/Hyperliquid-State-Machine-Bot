# 1. Import the utility file and other necessary libraries
import example_utils
from hyperliquid.utils import constants
import time # <-- Add this line to import the time library

def main():
    # 2. Use the setup function
    address, info, exchange = example_utils.setup(constants.MAINNET_API_URL, skip_ws=True)
    print(f"Successfully set up trading for address: {address}")

    # 3. Define your trade parameters
    coin = "LTC"
    is_buy = True 
    #leverage = 10 # <-- Define your desired leverage
    
    # --- NEW: Set leverage before trading ---
    #print(f"Setting leverage for {coin} to {leverage}x...")
    #leverage_result = exchange.update_leverage(leverage, coin, int(time.time() * 1000))

    # Check if setting leverage was successful
    #if leverage_result["status"] != "ok":
    #     print(f"Failed to set leverage: {leverage_result}")
    #     return
    # --- End of new section ---

    # 4. Now you can place the trade
    # Get the market price to calculate order size
    all_mids = info.all_mids()
    market_price = float(all_mids[coin])
    order_size_in_asset = round(250 / market_price, 2) # $50 worth of the asset

   # print(f"Attempting to market buy {order_size_in_asset} {coin} at {leverage}x leverage...")

    # Place the order using the 'exchange' object
    order_result = exchange.market_open(coin, is_buy, order_size_in_asset, None, 0.01)

    # Print the result
    print(order_result)


if __name__ == "__main__":
    main()