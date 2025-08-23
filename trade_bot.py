# trade_bot.py
import example_utils
from hyperliquid.utils import constants
import time
import json
import os
from datetime import datetime, timedelta
from db_manager import DatabaseManager
import requests # Added for Discord webhooks

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

def send_discord_notification(webhook_url, message=None, embed=None):
    """Sends a notification to the specified Discord webhook."""
    if not webhook_url:
        return # Don't send if webhook is not configured
    data = {}
    if message:
        data["content"] = message
    if embed:
        data["embeds"] = [embed]
    
    try:
        response = requests.post(webhook_url, json=data)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[!] Error sending Discord notification: {e}")

def read_last_savant_record():
    """Reads the last complete JSON object from the price_savant.json file."""
    if not os.path.exists(PRICE_SAVANT_FILE): return None
    try:
        with open(PRICE_SAVANT_FILE, 'rb') as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            if file_size == 0: return None
            buffer_size = 8192
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
            if last_obj_end != -1:
                return json.loads(temp_buffer[:last_obj_end])
            return None
    except Exception as e:
        print(f"[!] Error in read_last_savant_record: {e}")
        return None

def manage_stop_loss(asset, pos_info, db, savant_data, info, webhook_url):
    """
    Manages the stop loss logic for a given position.
    - Uses a fixed percentage stop loss initially.
    - Switches to a trailing stop using wma_fib_0 once fib_entry crosses the entry price.
    - Also handles the take profit condition.

    Returns (should_close, reason, value) tuple.
    """
    global position_data

    roe = float(pos_info["returnOnEquity"])
    entry_price = float(pos_info["entryPx"])
    current_price = float(info.all_mids().get(asset, 0))
    wma_fib_0 = savant_data.get("wma_fib_0") if savant_data else None
    fib_entry = savant_data.get("fib_entry") if savant_data else None

    if asset not in position_data:
        position_data[asset] = {
            'fib_stop_active': False,
            'stop_price': None,
        }
        print(f"[*] New position detected for {asset}. Entry: ${entry_price:,.2f}. Monitoring...")
        db.log_event("NEW_POSITION_MONITORING", {"asset": asset, "entry_price": entry_price})

    asset_state = position_data[asset]

    if fib_entry is not None and wma_fib_0 is not None and fib_entry > entry_price:
        if not asset_state['fib_stop_active']:
            asset_state['fib_stop_active'] = True
            asset_state['stop_price'] = wma_fib_0
            print(f"[*] FIB-TRAIL ACTIVATED for {asset}. fib_entry (${fib_entry:,.2f}) > entry (${entry_price:,.2f}).")
            print(f"    Initial Stop Price set to wma_fib_0: ${wma_fib_0:,.2f}")
            
            # --- Discord Notification for Fib Stop Activation ---
            embed = {
                "title": "🛡️ Fibonacci Stop Activated",
                "color": 3447003, # Blue
                "fields": [
                    {"name": "Asset", "value": asset, "inline": True},
                    {"name": "Entry Price", "value": f"${entry_price:,.2f}", "inline": True},
                    {"name": "Trigger (fib_entry)", "value": f"${fib_entry:,.2f}", "inline": True},
                    {"name": "Initial Stop Price (wma_fib_0)", "value": f"${wma_fib_0:,.2f}", "inline": False}
                ],
                "timestamp": datetime.utcnow().isoformat()
            }
            send_discord_notification(webhook_url, embed=embed)
            
            db.log_event("FIB_STOP_ACTIVATED", {
                "asset": asset,
                "trigger_value_fib_entry": fib_entry,
                "wma_fib_0_stop_price": wma_fib_0,
                "entry_price": entry_price,
            })
        elif wma_fib_0 > asset_state['stop_price']:
            old_stop = asset_state['stop_price']
            asset_state['stop_price'] = wma_fib_0
            print(f"[*] FIB-TRAIL UPDATED for {asset}: Stop moved up from ${old_stop:,.2f} to ${wma_fib_0:,.2f}")

    if asset_state['fib_stop_active']:
        if current_price <= asset_state['stop_price']:
            return True, "FIB-TRAIL-STOP", asset_state['stop_price']
    else:
        if roe <= -STOP_LOSS_PERCENTAGE:
            return True, "STOP-LOSS", f"{roe:.2%}"

    if roe >= TAKE_PROFIT_PERCENTAGE:
        return True, "TAKE-PROFIT", f"{roe:.2%}"

    return False, None, None

# --- MAIN EXECUTION ---
def main():
    global last_traded_signal_timestamp, last_known_trigger_state, last_trade_time, position_data

    config = load_config()
    if not config:
        return
    webhook_url = config.get("discord_webhook_url")

    db = DatabaseManager()

    try:
        print("--- Hyperliquid Trading Bot (Driver) ---")
        address, info, exchange = example_utils.setup(constants.MAINNET_API_URL, skip_ws=True)
        print(f"[*] Wallet: {address}")

        db.log_event("BOT_STARTED", {"message": "Trading bot has started."})
        send_discord_notification(webhook_url, message="✅ **Trading Bot Started**")
        
        print(f"\n[*] Bot Configuration:")
        print(f"    Fixed SL: {STOP_LOSS_PERCENTAGE:.2%}")
        print(f"    Take Profit: {TAKE_PROFIT_PERCENTAGE:.2%}")
        print(f"    Fib Trailing Stop: Activates when fib_entry > entry price")
        print("-" * 50)

        while True:
            latest_record = read_last_savant_record()

            try:
                user_state = info.user_state(address)
                positions = user_state.get("assetPositions", [])

                for pos in positions:
                    pos_info = pos["position"]
                    if float(pos_info["szi"]) == 0:
                        if pos_info["coin"] in position_data:
                            del position_data[pos_info["coin"]]
                        continue

                    asset = pos_info["coin"]
                    size = float(pos_info["szi"])
                    entry_px = float(pos_info["entryPx"])
                    roe = float(pos_info['returnOnEquity'])

                    should_close, reason, value = manage_stop_loss(asset, pos_info, db, latest_record, info, webhook_url)

                    if should_close:
                        print(f"\n[!!] {reason} TRIGGERED for {asset}!")
                        print(f"     Current ROE: {roe:.2%}")
                        print(f"     Trigger Value: {value}")

                        exchange.market_open(asset, size < 0, abs(size), None, 0.01)
                        db.update_position(asset, "N/A", 0, 0, "CLOSED")

                        # --- Discord Notification for Position Close ---
                        color = 15158332 if "STOP" in reason else 3066993 # Red for stop, Green for profit
                        embed = {
                            "title": f"🔒 Position Closed: {reason}",
                            "color": color,
                            "fields": [
                                {"name": "Asset", "value": asset, "inline": True},
                                {"name": "Size", "value": str(abs(size)), "inline": True},
                                {"name": "Final ROE", "value": f"{roe:.2%}", "inline": True},
                                {"name": "Entry Price", "value": f"${entry_px:,.2f}", "inline": True},
                                {"name": "Trigger Value", "value": str(value), "inline": True},
                            ],
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        send_discord_notification(webhook_url, embed=embed)

                        if asset in position_data:
                            del position_data[asset]

                        last_trade_time = datetime.now()
                        time.sleep(5)
                        break

            except Exception as e:
                print(f"[!] Error during position management: {e}")

            if latest_record:
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

                    order_result = exchange.market_open(coin, True, order_size, None, 0.01)

                    if order_result.get("status") == "ok":
                        filled_order = order_result['response']['data']['statuses'][0]['filled']
                        avg_px = float(filled_order['avgPx'])

                        db.update_position(coin, "LONG", order_size, avg_px, "OPEN")
                        print(f"[*] Trade Executed: Bought {order_size} {coin} @ ${avg_px:,.2f}")

                        # --- Discord Notification for New Trade ---
                        embed = {
                            "title": "🚀 New Trade Executed",
                            "color": 3066993, # Green
                            "fields": [
                                {"name": "Asset", "value": coin, "inline": True},
                                {"name": "Side", "value": "LONG", "inline": True},
                                {"name": "Size", "value": str(order_size), "inline": True},
                                {"name": "Average Price", "value": f"${avg_px:,.2f}", "inline": True},
                                {"name": "Value", "value": f"${(order_size * avg_px):,.2f}", "inline": True},
                            ],
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        send_discord_notification(webhook_url, embed=embed)

                        last_traded_signal_timestamp = latest_record.get('timestamp')
                        last_trade_time = datetime.now()
                    else:
                        print("[!] Trade Failed!")
                        send_discord_notification(webhook_url, message=f"❌ **Trade Failed!** Reason: `{str(order_result)}`")

            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n[*] Bot stopped by user.")
        db.log_event("BOT_STOPPED", {"message": "Bot stopped by user."})
        send_discord_notification(webhook_url, message="🛑 **Trading Bot Stopped by user.**")
    except Exception as e:
        print(f"[!!!] CRITICAL ERROR: {e}")
        db.log_event("CRITICAL_ERROR", {"error": str(e)})
        send_discord_notification(webhook_url, message=f"🚨 **CRITICAL ERROR!**\n```{e}```")

if __name__ == "__main__":
    main()
