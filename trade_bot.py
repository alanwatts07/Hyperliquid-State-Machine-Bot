# trade_bot.py
import example_utils
from hyperliquid.utils import constants
import time
import json
import os
from datetime import datetime, timedelta
from db_manager import DatabaseManager

# --- Script Configuration ---
PRICE_SAVANT_FILE = "price_savant.json"
CONFIG_FILE = "config.json"
CHECK_INTERVAL_SECONDS = 5
TRADE_USD_SIZE = 625
TRADE_ASSET = "SOL"
TRADE_COOLDOWN_MINUTES = 10
STOP_LOSS_PERCENTAGE = 0.45
TAKE_PROFIT_PERCENTAGE = 2.15

# --- State Tracking ---
last_traded_signal_timestamp = None
last_known_trigger_state = None
last_trade_time = None
# Updated position_data to track the state of our new stop logic
position_data = {}

# --- Helper Functions ---
def load_config():
    """Loads the main config.json file."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"[!!!] CRITICAL: `{CONFIG_FILE}` not found or corrupt.")
        return None

def read_last_savant_record():
    """Reads the last complete JSON object from the price_savant.json file."""
    if not os.path.exists(PRICE_SAVANT_FILE): return None
    try:
        with open(PRICE_SAVANT_FILE, 'rb') as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            if file_size == 0: return None
            # Read a larger buffer to ensure we get a full JSON object
            buffer_size = 8192
            seek_pos = max(0, file_size - buffer_size)
            f.seek(seek_pos)
            buffer = f.read().decode('utf-8', errors='ignore')
            # Find the last '{' to start parsing from a potential JSON object
            last_obj_start = buffer.rfind('{')
            if last_obj_start == -1: return None
            temp_buffer = buffer[last_obj_start:]
            # Find the matching '}' to ensure the JSON object is complete
            brace_level, last_obj_end = 0, -1
            for i, char in enumerate(temp_buffer):
                if char == '{': brace_level += 1
                elif char == '}' and brace_level > 0:
                    brace_level -= 1
                    if brace_level == 0:
                        last_obj_end = i + 1
                        break
            if last_obj_end != -1:
                return json.loads(temp_buffer[:last_obj_end])
            return None
    except Exception as e:
        print(f"[!] Error in read_last_savant_record: {e}")
        return None

def manage_stop_loss(asset, pos_info, db, savant_data, info):
    """
    Manages the stop loss logic for a given position.
    - Uses a fixed percentage stop loss initially.
    - Switches to a trailing stop using wma_fib_0 once it crosses the entry price.
    - Also handles the take profit condition.

    Returns (should_close, reason, value) tuple.
    """
    global position_data

    # Extract key info from the position and market data
    roe = float(pos_info["returnOnEquity"])
    entry_price = float(pos_info["entryPx"])
    current_price = float(info.all_mids().get(asset, 0))
    wma_fib_0 = savant_data.get("wma_fib_0") if savant_data else None

    # Initialize tracking for a new position
    if asset not in position_data:
        position_data[asset] = {
            'fib_stop_active': False,
            'stop_price': None, # This will be the price level for our stop
        }
        print(f"[*] New position detected for {asset}. Entry: ${entry_price:,.2f}. Monitoring...")
        db.log_event("NEW_POSITION_MONITORING", {"asset": asset, "entry_price": entry_price})


    asset_state = position_data[asset]

    # --- Main Stop Logic ---

    # 1. Check if we should activate or update the Fibonacci trailing stop
    if wma_fib_0 is not None and wma_fib_0 > entry_price:
        if not asset_state['fib_stop_active']:
            asset_state['fib_stop_active'] = True
            asset_state['stop_price'] = wma_fib_0
            print(f"[*] FIB-TRAIL ACTIVATED for {asset}. wma_fib_0 (${wma_fib_0:,.2f}) > entry (${entry_price:,.2f}).")
            print(f"    Initial Stop Price set to: ${wma_fib_0:,.2f}")
            db.log_event("FIB_STOP_ACTIVATED", {
                "asset": asset,
                "wma_fib_0": wma_fib_0,
                "entry_price": entry_price,
                "initial_stop_price": wma_fib_0
            })
        # If already active, only move the stop up, never down
        elif wma_fib_0 > asset_state['stop_price']:
            old_stop = asset_state['stop_price']
            asset_state['stop_price'] = wma_fib_0
            print(f"[*] FIB-TRAIL UPDATED for {asset}: Stop moved up from ${old_stop:,.2f} to ${wma_fib_0:,.2f}")

    # 2. Check if any stop condition is met
    if asset_state['fib_stop_active']:
        # Use the Fibonacci trailing stop price
        if current_price <= asset_state['stop_price']:
            return True, "FIB-TRAIL-STOP", asset_state['stop_price']
    else:
        # Use the initial fixed percentage stop loss
        if roe <= -STOP_LOSS_PERCENTAGE:
            return True, "STOP-LOSS", f"{roe:.2%}"

    # 3. Check for take profit, which is always active
    if roe >= TAKE_PROFIT_PERCENTAGE:
        return True, "TAKE-PROFIT", f"{roe:.2%}"

    return False, None, None


# --- MAIN EXECUTION ---
def main():
    global last_traded_signal_timestamp, last_known_trigger_state, last_trade_time, position_data

    db = DatabaseManager()

    try:
        print("--- Hyperliquid Trading Bot (Driver) ---")
        address, info, exchange = example_utils.setup(constants.MAINNET_API_URL, skip_ws=True)
        print(f"[*] Wallet: {address}")

        db.log_event("BOT_STARTED", {"message": "Trading bot has started."})
        print(f"\n[*] Bot Configuration:")
        print(f"    Fixed SL: {STOP_LOSS_PERCENTAGE:.2%}")
        print(f"    Take Profit: {TAKE_PROFIT_PERCENTAGE:.2%}")
        print(f"    Fib Trailing Stop: Activates when wma_fib_0 > entry price")
        print("-" * 50)

        while True:
            # Command & Control Check
            try:
                command_status = db.get_command("CLOSE_ALL")
                if command_status == "CONFIRMED":
                    print("\n[!!!] CLOSE ALL COMMAND RECEIVED FROM DISCORD!")

                    user_state = info.user_state(address)
                    positions = user_state.get("assetPositions", [])
                    open_positions = [p for p in positions if float(p["position"]["szi"]) != 0]

                    if not open_positions:
                        print("[*] Close command received, but no positions were open.")

                    for pos in open_positions:
                        pos_info = pos["position"]
                        asset, size = pos_info["coin"], float(pos_info["szi"])
                        print(f"[*] Closing {asset} position of size {size}...")

                        exchange.market_open(asset, size < 0, abs(size), None, 0.01)
                        db.update_position(asset, "N/A", 0, 0, "CLOSED")

                        # Clear position tracking
                        if asset in position_data:
                            del position_data[asset]

                    db.log_event("COMMAND_EXECUTED", {"command": "CLOSE_ALL", "closed_count": len(open_positions)})
                    db.set_command("CLOSE_ALL", "EXECUTED")

                    print("[*] All positions closed. Activating cooldown.")
                    last_trade_time = datetime.now()
            except Exception as e:
                print(f"[!] Error during command check: {e}")

            # Read savant data once per loop iteration before managing positions
            latest_record = read_last_savant_record()

            # Position Management
            try:
                user_state = info.user_state(address)
                positions = user_state.get("assetPositions", [])

                for pos in positions:
                    pos_info = pos["position"]
                    if float(pos_info["szi"]) == 0:
                        # If a position is closed, ensure we clean up its tracking data
                        if pos_info["coin"] in position_data:
                            del position_data[pos_info["coin"]]
                        continue

                    asset = pos_info["coin"]
                    size = float(pos_info["szi"])

                    # Pass all necessary data to the stop loss manager
                    should_close, reason, value = manage_stop_loss(asset, pos_info, db, latest_record, info)

                    if should_close:
                        print(f"\n[!!] {reason} TRIGGERED for {asset}!")
                        print(f"     Current ROE: {float(pos_info['returnOnEquity']):.2%}")
                        print(f"     Trigger Value: {value}")

                        exchange.market_open(asset, size < 0, abs(size), None, 0.01)
                        db.update_position(asset, "N/A", 0, 0, "CLOSED")

                        # Log detailed close information
                        close_data = {
                            "asset": asset,
                            "size": abs(size),
                            "roe": float(pos_info['returnOnEquity']),
                            "reason": reason,
                            "trigger_value": value
                        }
                        if asset in position_data:
                            close_data.update(position_data[asset])
                            del position_data[asset] # Clean up state

                        db.log_event(f"{reason}_HIT", close_data)

                        print("[*] Position closed. Activating trade cooldown.")
                        last_trade_time = datetime.now()
                        time.sleep(5) # Brief pause to allow systems to update
                        break # Exit loop to re-fetch positions

                    # Display position status periodically
                    elif asset in position_data and int(time.time()) % 30 == 0: # Every 30 seconds
                        state = position_data[asset]
                        if state['fib_stop_active']:
                            print(f"[~] {asset}: ROE {float(pos_info['returnOnEquity']):.2%} | Fib Stop Active @ ${state['stop_price']:,.2f}")
                        else:
                            print(f"[~] {asset}: ROE {float(pos_info['returnOnEquity']):.2%} | Awaiting Fib Stop Activation")


            except Exception as e:
                print(f"[!] Error during position management: {e}")

            # Signal Monitoring & Event Logging
            if latest_record:
                # Detect and log trigger state changes
                current_trigger_armed = latest_record.get('trigger_armed')
                if current_trigger_armed is not None and current_trigger_armed != last_known_trigger_state:
                    if current_trigger_armed:
                        db.log_event("TRIGGER_ARMED", {"savant_data": latest_record})
                    else:
                        db.log_event("TRIGGER_DISARMED", {"savant_data": latest_record})
                    last_known_trigger_state = current_trigger_armed

                # Check for a new buy signal to trade on
                if latest_record.get('buy_signal') and latest_record.get('timestamp') != last_traded_signal_timestamp:
                    if last_trade_time and (datetime.now() - last_trade_time) < timedelta(minutes=TRADE_COOLDOWN_MINUTES):
                        last_traded_signal_timestamp = latest_record.get('timestamp')
                        continue

                    print(f"\n[!] New Buy Signal Detected!")
                    coin = TRADE_ASSET
                    meta = info.meta()
                    sz_decimals = next((asset["szDecimals"] for asset in meta["universe"] if asset["name"] == coin), 2)
                    market_price = float(info.all_mids()[coin])
                    order_size = round(TRADE_USD_SIZE / market_price, sz_decimals)

                    db.log_event("BUY_SIGNAL", {"savant_data": latest_record})
                    order_result = exchange.market_open(coin, True, order_size, None, 0.01)

                    if order_result.get("status") == "ok":
                        filled_order = order_result['response']['data']['statuses'][0]['filled']
                        avg_px = float(filled_order['avgPx'])

                        db.update_position(coin, "LONG", order_size, avg_px, "OPEN")
                        db.log_event("TRADE_EXECUTED", {"asset": coin, "size": order_size, "avg_px": avg_px})

                        print(f"[*] Trade Executed: Bought {order_size} {coin} @ ${avg_px:,.2f}")
                        last_traded_signal_timestamp = latest_record.get('timestamp')
                        last_trade_time = datetime.now()
                    else:
                        db.log_event("TRADE_FAILED", {"reason": str(order_result)})
                        print("[!] Trade Failed!")

            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        db.log_event("BOT_STOPPED", {"message": "Bot stopped by user."})
        print("\n[*] Bot stopped by user.")
    except Exception as e:
        print(f"[!!!] CRITICAL ERROR: {e}")
        db.log_event("CRITICAL_ERROR", {"error": str(e)})

if __name__ == "__main__":
    main()
