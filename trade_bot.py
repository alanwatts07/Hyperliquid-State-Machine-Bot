# Hyperliquid Trade Execution Bot with Alerts (Savant Reader Integration)
#
# This script has been modified to read 'price_savant.json' directly.
# This approach makes it the single source of truth and avoids race conditions.
#
# It checks the last record in the savant file for a 'buy_signal'.
# To prevent duplicate trades, it keeps track of the timestamp of the
# last signal it successfully traded.
#
# NEW: The hourly "alive" status update now includes the latest data snapshot.
#
# To Run:
# 1. Ensure 'collector.py' and the original 'app.py' are running.
# 2. Configure your trade size and Discord webhook URL.
# 3. Run this script from your terminal: python trade.py

import example_utils
from hyperliquid.utils import constants
import time
import json
import os
import requests
from datetime import datetime
import schedule # Import the schedule library

# --- Configuration ---
PRICE_SAVANT_FILE = "price_savant.json" # MODIFIED: Now reading from the main savant file
TRADE_LOG_FILE = "trade_log.json"
CHECK_INTERVAL_SECONDS = 5
TRADE_USD_SIZE = 225

# --- ALERT CONFIGURATION ---
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1404935802810794004/VLu3___9gBvUv-UnoekLGW9ziln5RoMXq31Z40ovXXonFchRI00ADgt9yc3B0GY_YkVI"
ENABLE_CONSOLE_ALERTS = True
ENABLE_DISCORD_ALERTS = bool(DISCORD_WEBHOOK_URL)

# --- State Tracking ---
# NEW: We now track trigger state changes as well.
last_traded_signal_timestamp = None
last_known_trigger_state = None

def send_discord_alert(message, color=0x00ff00, savant_data=None):
    """
    Send alert to Discord webhook.
    NEW: Can now include formatted savant data in the alert.
    """
    if not DISCORD_WEBHOOK_URL:
        return
    
    try:
        embed = {
            "title": "🤖 SOL Trading Bot Alert",
            "description": message,
            "color": color,
            "timestamp": datetime.now().isoformat(),
            "footer": {"text": "Hyperliquid Trading Bot (Savant Reader)"}
        }

        # NEW: Add detailed fields if savant_data is provided
        if savant_data:
            fields = [
                {"name": "Price", "value": f"`${savant_data.get('price', 0):.3f}`", "inline": True},
                {"name": "Trigger Armed", "value": f"**`{savant_data.get('trigger_armed', 'N/A')}`**", "inline": True},
                {"name": "Buy Signal", "value": f"**`{savant_data.get('buy_signal', 'N/A')}`**", "inline": True},
                {"name": "Fib Entry", "value": f"`${savant_data.get('fib_entry', 0):.3f}`", "inline": True},
                {"name": "Fib 0", "value": f"`${savant_data.get('wma_fib_0', 0):.3f}`", "inline": True},
                {"name": "ATR", "value": f"`{savant_data.get('atr', 0):.4f}`", "inline": True},
                {"name": "Timestamp", "value": f"`{savant_data.get('timestamp')}`", "inline": False},
            ]
            embed["fields"] = fields

        payload = {"embeds": [embed]}
        
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 204:
            if ENABLE_CONSOLE_ALERTS: print("[✓] Discord alert sent successfully")
        else:
            if ENABLE_CONSOLE_ALERTS: print(f"[!] Discord alert failed: {response.status_code} - {response.text}")
    except Exception as e:
        if ENABLE_CONSOLE_ALERTS: print(f"[!] Discord alert error: {e}")

def send_hourly_status_update():
    """
    MODIFIED: Sends a scheduled 'bot is alive' status update with current stats.
    """
    print("[*] Sending hourly status update...")
    message = f"✅ **Hourly Status Report.** Bot is alive and monitoring."
    
    # Read the latest data to include in the status update
    latest_record = read_last_savant_record()
    
    # The color 0x3498db is a standard blue
    send_discord_alert(message, 0x3498db, savant_data=latest_record)

def read_last_savant_record():
    """
    FIXED: Efficiently reads the last JSON object from the price_savant.json file.
    This version correctly isolates the last object to prevent JSON decoding errors.
    """
    if not os.path.exists(PRICE_SAVANT_FILE):
        return None
    try:
        with open(PRICE_SAVANT_FILE, 'rb') as f:
            buffer_size = 4096
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            if file_size == 0:
                return None

            seek_pos = max(0, file_size - buffer_size)
            f.seek(seek_pos)
            buffer = f.read(file_size - seek_pos).decode('utf-8', errors='ignore')

            last_obj_start = buffer.rfind('{')
            if last_obj_start == -1:
                return None

            temp_buffer = buffer[last_obj_start:]
            brace_level = 0
            last_obj_end = -1
            for i, char in enumerate(temp_buffer):
                if char == '{':
                    brace_level += 1
                elif char == '}':
                    brace_level -= 1
                    if brace_level == 0:
                        last_obj_end = i + 1
                        break
            
            if last_obj_end != -1:
                json_str = temp_buffer[:last_obj_end]
                return json.loads(json_str)
            else:
                return None

    except (json.JSONDecodeError, FileNotFoundError, OSError, IndexError) as e:
        if ENABLE_CONSOLE_ALERTS: print(f"[!] Error reading last savant record: {e}. Will retry.")
        return None

def log_trade(trigger_data, order_result, order_size, trade_type):
    """Appends the details of a trade attempt to the trade log file."""
    print(f"[*] Logging '{trade_type}' trade attempt...")
    log_entry = {
        "log_timestamp": datetime.now().isoformat(),
        "trade_type": trade_type,
        "trade_size_usd": TRADE_USD_SIZE,
        "calculated_asset_size": order_size,
        "trigger_data": trigger_data,
        "exchange_response": order_result
    }
    
    try:
        logs = []
        if os.path.exists(TRADE_LOG_FILE):
            with open(TRADE_LOG_FILE, 'r') as f:
                logs = json.load(f)
        logs.append(log_entry)
        with open(TRADE_LOG_FILE, 'w') as f:
            json.dump(logs, f, indent=4)
        print("[*] Trade logged successfully.")
    except Exception as e:
        print(f"[!] Error logging trade: {e}")

def main():
    """Main loop to check for signals and execute trades."""
    global last_traded_signal_timestamp, last_known_trigger_state
    try:
        print("--- Hyperliquid Trading Bot (Savant Reader Integration) ---")
        address, info, exchange = example_utils.setup(constants.MAINNET_API_URL, skip_ws=True)
        print(f"[*] Successfully set up trading for address: {address}")
        
        print(f"[*] Discord Alerts: {'✓ Enabled' if ENABLE_DISCORD_ALERTS else '✗ Disabled (no webhook)'}")
        
        print("[*] Scheduling hourly 'bot is alive' status update...")
        schedule.every().hour.at(":00").do(send_hourly_status_update)
        
        send_discord_alert(f"🤖 **Trading bot started.** Now monitoring `{PRICE_SAVANT_FILE}`...", 0x888888) # Gray for info
        print(f"\n[*] Bot is running. Scanning {PRICE_SAVANT_FILE} for signals...")
        print("-" * 50)

        while True:
            schedule.run_pending()
            
            latest_record = read_last_savant_record()
            
            if latest_record:
                is_buy_signal = latest_record.get('buy_signal', False)
                signal_timestamp = latest_record.get('timestamp')
                current_trigger_armed = latest_record.get('trigger_armed')

                # --- NEW: Check for trigger state changes ---
                if current_trigger_armed is not None and current_trigger_armed != last_known_trigger_state:
                    if current_trigger_armed:
                        # Trigger has become ARMED
                        message = "🟡 **Trigger ARMED!** Bot is now watching for price to cross above Fib 0."
                        send_discord_alert(message, 0xffff00, savant_data=latest_record)
                    else:
                        # Trigger has become DISARMED
                        message = "🔴 **Trigger DISARMED.** Price likely crossed the reset threshold."
                        send_discord_alert(message, 0xff6347, savant_data=latest_record)
                    last_known_trigger_state = current_trigger_armed

                # --- Check for a new, untraded buy signal ---
                if is_buy_signal and signal_timestamp != last_traded_signal_timestamp:
                    print(f"\n[!] New Buy Signal Detected at {signal_timestamp}!")
                    
                    message = f"🚀 **BUY SIGNAL DETECTED!**\nPreparing to execute trade..."
                    send_discord_alert(message, 0x00ff00, savant_data=latest_record) # Green for buy signal
                    
                    # --- EXECUTE THE TRADE ---
                    coin = "SOL"
                    is_buy = True
                    
                    meta = info.meta()
                    sz_decimals = next((asset["szDecimals"] for asset in meta["universe"] if asset["name"] == coin), 2)
                    market_price = float(info.all_mids()[coin])
                    order_size_in_asset = round(TRADE_USD_SIZE / market_price, sz_decimals)
                    
                    print(f"[*] Placing market buy order for {order_size_in_asset} {coin}...")
                    order_result = exchange.market_open(coin, is_buy, order_size_in_asset, None, 0.01)

                    print("[*] Trade Result:", order_result)
                    log_trade(latest_record, order_result, order_size_in_asset, "buy")

                    if order_result.get("status") == "ok":
                        avg_fill_price = float(order_result['response']['data']['statuses'][0]['filled']['avgPx'])
                        success_msg = f"✅ **TRADE EXECUTED!**\nBought **{order_size_in_asset} {coin}** at avg price **${avg_fill_price:,.2f}**."
                        send_discord_alert(success_msg, 0x0099ff) # Bright blue for trade success
                        
                        last_traded_signal_timestamp = signal_timestamp
                        print(f"[*] Marked signal from {signal_timestamp} as traded.")
                    else:
                        fail_msg = f"❌ **TRADE FAILED!** Order rejected by exchange. Check logs. The bot will retry on the next signal."
                        send_discord_alert(fail_msg, 0xff0000) # Red for error

                    print("\n[*] Resuming scan...")

            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        send_discord_alert("🛑 Trading bot stopped by user.", 0x888888)
        print("\n[*] Bot stopped by user. Goodbye!")
    except Exception as e:
        error_message = f"❌ A critical bot error occurred: {str(e)}"
        print(f"[!!!] CRITICAL ERROR: {e}")
        send_discord_alert(error_message, 0xff0000)
        time.sleep(5)

if __name__ == "__main__":
    main()
