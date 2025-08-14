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
STOP_LOSS_PERCENTAGE = 0.15
TAKE_PROFIT_PERCENTAGE = 0.30

# --- State Tracking ---
last_traded_signal_timestamp = None
last_known_trigger_state = None
last_trade_time = None

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
            buffer_size = 4096
            seek_pos = max(0, file_size - buffer_size)
            f.seek(seek_pos)
            buffer = f.read().decode('utf-8', errors='ignore')
            last_obj_start = buffer.rfind('{')
            if last_obj_start == -1: return None
            temp_buffer = buffer[last_obj_start:]
            brace_level, last_obj_end = 0, -1
            for i, char in enumerate(temp_buffer):
                if char == '{': brace_level += 1
                elif char == '}' and brace_level > 0:
                    brace_level -= 1
                    if brace_level == 0:
                        last_obj_end = i + 1
                        break
            if last_obj_end != -1: return json.loads(temp_buffer[:last_obj_end])
            return None
    except Exception as e:
        print(f"[!] Error in read_last_savant_record: {e}")
        return None

# --- MAIN EXECUTION ---
def main():
    global last_traded_signal_timestamp, last_known_trigger_state, last_trade_time
    
    db = DatabaseManager()
    
    try:
        print("--- Hyperliquid Trading Bot (Driver) ---")
        address, info, exchange = example_utils.setup(constants.MAINNET_API_URL, skip_ws=True)
        print(f"[*] Wallet: {address}")
        
        db.log_event("BOT_STARTED", {"message": "Trading bot has started."})
        print(f"\n[*] Bot running... SL: {STOP_LOSS_PERCENTAGE:.0%}, TP: {TAKE_PROFIT_PERCENTAGE:.0%}")
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
                    
                    db.log_event("COMMAND_EXECUTED", {"command": "CLOSE_ALL", "closed_count": len(open_positions)})
                    db.set_command("CLOSE_ALL", "EXECUTED") # Mark as done
                    
                    print("[*] All positions closed. Activating cooldown.")
                    last_trade_time = datetime.now()
            except Exception as e:
                print(f"[!] Error during command check: {e}")

            # Position Management (SL/TP)
            try:
                user_state = info.user_state(address)
                positions = user_state.get("assetPositions", [])
                for pos in positions:
                    pos_info = pos["position"]
                    roe = float(pos_info["returnOnEquity"])
                    should_close, reason = False, ""

                    if roe <= -STOP_LOSS_PERCENTAGE:
                        should_close, reason = True, "STOP-LOSS"
                    elif roe >= TAKE_PROFIT_PERCENTAGE:
                        should_close, reason = True, "TAKE-PROFIT"

                    if should_close:
                        asset, size = pos_info["coin"], float(pos_info["szi"])
                        print(f"\n[!!] {reason} TRIGGERED for {asset}! ROE: {roe:.2%}")
                        
                        exchange.market_open(asset, size < 0, abs(size), None, 0.01)
                        db.update_position(asset, "N/A", 0, 0, "CLOSED")
                        db.log_event(f"{reason}_HIT", {"asset": asset, "size": abs(size), "roe": roe})
                        
                        print("[*] Position closed. Activating trade cooldown.")
                        last_trade_time = datetime.now()
                        time.sleep(5)
                        break
            except Exception as e:
                print(f"[!] Error during position management: {e}")

            # Signal Monitoring & Event Logging
            latest_record = read_last_savant_record()
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