from hyperliquid.info import Info
from hyperliquid.utils import constants

def main():
    # Address provided by the user.
    user_address = "0x9c57e3F5115D34ce90Dfc8E3408698a566aD2771"
    
    print(f"📈 Fetching open positions for wallet: {user_address}\n")
    
    # Initialize the Info client for the mainnet
    info = Info(constants.MAINNET_API_URL, skip_ws=True)

    try:
        # Get the user's state
        user_state = info.user_state(user_address)
        
        # Filter for asset positions that are actually open
        asset_positions = user_state.get("assetPositions", [])
        open_positions = [p for p in asset_positions if float(p["position"]["szi"]) != 0]

        if not open_positions:
            print("No open positions found for this wallet.")
            return

        print(f"Found {len(open_positions)} open position(s):")
        print("-" * 70)

        for position in open_positions:
            pos_info = position["position"]
            asset = pos_info["coin"]
            
            position_size_coins = float(pos_info["szi"])
            direction = "LONG" if position_size_coins > 0 else "SHORT"
            
            entry_price = float(pos_info["entryPx"])
            position_value_usd = float(pos_info["positionValue"])
            unrealized_pnl = float(pos_info["unrealizedPnl"])
            leverage = float(pos_info["leverage"]["value"])

            print(f"  Asset: {asset}")
            print(f"    Direction: {direction}")
            print(f"    Size (Coins): {abs(position_size_coins):.4f} {asset}")
            print(f"    Size (USD): ${position_value_usd:,.2f}")
            print(f"    Entry Price: ${entry_price:,.4f}")
            print(f"    Leverage: {leverage:.2f}x")
            print(f"    Unrealized PnL: ${unrealized_pnl:,.2f}")
            print("-" * 70)

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()