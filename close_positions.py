## Because if you never close your trade, you are a broke skid. 
# A script to close open positions on Hyperliquid
import example_utils
from hyperliquid.utils import constants
import time

def close_all_positions():
    """
    Fetches all open positions and provides an interactive prompt to close each one.
    """
    try:
        # We need the 'exchange' object to place trades
        address, info, exchange = example_utils.setup(constants.MAINNET_API_URL, skip_ws=True)
        print(f"✅ Sucessfully connected to wallet: {address}")
        print("-" * 50)
    except Exception as e:
        print(f"❌ Error setting up connection: {e}")
        return

    # 1. Fetch all open positions
    try:
        user_state = info.user_state(address)
        asset_positions = user_state.get("assetPositions", [])
        open_positions = [p for p in asset_positions if float(p["position"]["szi"]) != 0]
    except Exception as e:
        print(f"❌ Could not fetch open positions: {e}")
        return

    if not open_positions:
        print("🟢 No open positions found.")
        return

    print(f"Found {len(open_positions)} open position(s).")

    # 2. Loop through each position and offer to close it
    for position in open_positions:
        pos_info = position["position"]
        asset = pos_info["coin"]
        size = float(pos_info["szi"])
        direction = "LONG" if size > 0 else "SHORT"
        
        # 3. Determine the parameters for the closing trade
        is_buy_for_close = (direction == "SHORT") # If we are SHORT, we need to BUY to close
        action_word = "SELL" if direction == "LONG" else "BUY"
        size_to_close = abs(size)

        print("\n" + "=" * 50)
        print(f"  Position Found: {direction} {size_to_close} {asset}")
        print(f"  Entry Price: ${float(pos_info['entryPx']):,.2f}")
        print(f"  Unrealized PnL: ${float(pos_info['unrealizedPnl']):,.2f}")
        print(f"  Proposed Action: Market {action_word} {size_to_close} {asset}")
        print("=" * 50)

        # 4. Get confirmation from the user
        try:
            confirm = input("❓ Do you want to execute this closing trade? (y/n): ").lower().strip()
        except KeyboardInterrupt:
            print("\n🛑 Operation cancelled by user.")
            break
            
        if confirm == 'y':
            print(f"🚀 Executing closing trade for {asset}...")
            try:
                # 5. Execute the closing market order
                order_result = exchange.market_open(
                    coin=asset,
                    is_buy=is_buy_for_close,
                    sz=size_to_close,
                    px=None, # Market order
                    slippage=0.01 # Allow 1% slippage
                )

                if order_result.get("status") == "ok":
                    print("✅ SUCCESS! Trade closed successfully.")
                    print(f"   Response: {order_result['response']}")
                else:
                    print("❌ FAILED! The trade could not be closed.")
                    print(f"   Error: {order_result}")

            except Exception as e:
                print(f"❌ An unexpected error occurred during trade execution: {e}")
        else:
            print("Skipping this position.")

    print("\n✅ Script finished.")

if __name__ == "__main__":
    close_all_positions()