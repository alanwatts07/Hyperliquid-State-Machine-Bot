# Hyperliquid All-in-One Bot - Final Version
import example_utils
from hyperliquid.utils import constants
import time
import json
import os
import requests
from datetime import datetime, timezone
import schedule

# --- Configuration ---
PRICE_SAVANT_FILE = "price_savant.json"
TRADE_LOG_FILE = "trade_log.json"
CHECK_INTERVAL_SECONDS = 5
TRADE_USD_SIZE = 625
TRADE_ASSET = "SOL"
TRADE_COOLDOWN_MINUTES = 10
STATUS_UPDATE_MINUTES = 15
STOP_LOSS_PERCENTAGE = 0.15
TAKE_PROFIT_PERCENTAGE = 0.30

# --- ALERT CONFIGURATION ---
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1404935802810794004/VLu3___9gBvUv-UnoekLGW9ziln5RoMXq31Z40ovXXonFchRI00ADgt9yc3B0GY_YkVI"
ENABLE_CONSOLE_ALERTS = True

# --- State Tracking ---
last_traded_signal_timestamp = None
last_known_trigger_state = None
last_trade_time = None

# (Helper functions like format_timedelta, load_trade_log remain the same)
def format_timedelta(td):
    seconds = int(td.total_seconds())
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    parts = [f"{d}d" for d in [days] if d > 0]
    parts.extend([f"{h}h" for h in [hours] if h > 0])
    parts.extend([f"{m}m" for m in [minutes] if m > 0])
    return " ".join(parts) if parts else "< 1 min"
def load_trade_log(filepath='trade_log.json'):
    try:
        with open(filepath, 'r') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return []

# <-- MODIFIED: Restored the original, robust function to read the last JSON object
def read_last_savant_record():
    """Efficiently reads the last complete JSON object from the price_savant.json file."""
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

            # Find the start of the last JSON object
            last_obj_start = buffer.rfind('{')
            if last_obj_start == -1: return None

            # Find the corresponding end brace to isolate the object
            temp_buffer = buffer[last_obj_start:]
            brace_level = 0
            last_obj_end = -1
            for i, char in enumerate(temp_buffer):
                if char == '{': brace_level += 1
                elif char == '}':
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

# (The rest of the script is unchanged)
def get_open_positions(address, info, trade_log):
    try:
        user_state = info.user_state(address)
        asset_positions = user_state.get("assetPositions", [])
        open_positions = [p for p in asset_positions if float(p["position"]["szi"]) != 0]
        processed_positions = []
        for position in open_positions:
            pos_info = position["position"]
            live_asset = pos_info["coin"]
            live_size = float(pos_info["szi"])
            time_open_str = "Match not in log"
            for log_entry in trade_log:
                if (log_entry.get("coin") == live_asset and
                    abs(abs(live_size) - log_entry.get("calculated_asset_size", 0)) < 0.01):
                    trade_time = datetime.fromisoformat(log_entry['log_timestamp'])
                    time_open_str = f"{format_timedelta(datetime.now() - trade_time)} old"
                    break
            processed_positions.append({
                "asset": live_asset, "direction": "LONG" if live_size > 0 else "SHORT",
                "size": abs(live_size), "entry_px": float(pos_info['entryPx']),
                "pnl": float(pos_info['unrealizedPnl']), "time_open": time_open_str
            })
        return processed_positions
    except Exception: return []
def send_discord_alert(message, color=0x00ff00, savant_data=None, open_positions=None):
    if not DISCORD_WEBHOOK_URL: return
    try:
        embed = {"title": f"🤖 {TRADE_ASSET} Trading Bot Alert", "description": message, "color": color, "timestamp": datetime.now().isoformat(), "footer": {"text": "Hyperliquid All-in-One Bot"}}
        fields = []
        if savant_data:
            fields.extend([
                {"name": "Price", "value": f"`${savant_data.get('price', 0):.3f}`", "inline": True},
                {"name": "Trigger Armed", "value": f"**`{savant_data.get('trigger_armed', 'N/A')}`**", "inline": True},
                {"name": "Buy Signal", "value": f"**`{savant_data.get('buy_signal', 'N/A')}`**", "inline": True},
                {"name": "Fib Entry", "value": f"`${savant_data.get('fib_entry', 0):.3f}`", "inline": True},
                {"name": "Fib 0", "value": f"`${savant_data.get('wma_fib_0', 0):.3f}`", "inline": True},
                {"name": "ATR", "value": f"`{savant_data.get('atr', 0):.4f}`", "inline": True},
                {"name": "Timestamp", "value": f"`{savant_data.get('timestamp')}`", "inline": False},
            ])
        if open_positions:
            for pos in open_positions:
                pnl_emoji = "🔼" if pos['pnl'] >= 0 else "🔽"
                pnl_str = f"${pos['pnl']:,.2f}"
                field_value = (f"**`{pos['direction']} {pos['size']:.4f} {pos['asset']}`**\n" f"**Entry:** `${pos['entry_px']:,.2f}`\n" f"**PnL:** `{pnl_emoji} {pnl_str}`\n" f"**Age:** `{pos['time_open']}`")
                fields.append({"name": f"📊 Open Position: {pos['asset']}", "value": field_value, "inline": False})
        if fields: embed["fields"] = fields
        requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)
    except Exception as e:
        if ENABLE_CONSOLE_ALERTS: print(f"[!] Discord alert error: {e}")
def send_status_update(address, info):
    print(f"[*] Sending {STATUS_UPDATE_MINUTES}-minute status update...")
    trade_log = load_trade_log()
    positions = get_open_positions(address, info, trade_log)
    latest_savant_data = read_last_savant_record()
    message = f"✅ **{STATUS_UPDATE_MINUTES}-Minute Status Report.** Bot is alive and monitoring."
    if not positions: message += "\nNo open positions."
    send_discord_alert(message, 0x3498db, savant_data=latest_savant_data, open_positions=positions)
def log_trade(coin, trigger_data, order_result, order_size, trade_type):
    log_entry = { "log_timestamp": datetime.now().isoformat(), "coin": coin, "trade_type": trade_type, "trade_size_usd": TRADE_USD_SIZE, "calculated_asset_size": order_size, "trigger_data": trigger_data, "exchange_response": order_result }
    try:
        logs = load_trade_log()
        logs.append(log_entry)
        with open(TRADE_LOG_FILE, 'w') as f: json.dump(logs, f, indent=4)
    except Exception as e: print(f"[!] CRITICAL Error logging trade: {e}")
def main():
    global last_traded_signal_timestamp, last_known_trigger_state, last_trade_time
    try:
        print("--- Hyperliquid Bot w/ SL, TP, & Full Alerts ---")
        address, info, exchange = example_utils.setup(constants.MAINNET_API_URL, skip_ws=True)
        print(f"[*] Wallet: {address}")
        schedule.every(STATUS_UPDATE_MINUTES).minutes.do(send_status_update, address=address, info=info)
        startup_msg = (f"🤖 **Bot Started.** Monitoring **{TRADE_ASSET}**\n" f"**Stop-Loss:** `{STOP_LOSS_PERCENTAGE:.0%}`\n" f"**Take-Profit:** `{TAKE_PROFIT_PERCENTAGE:.0%}`")
        send_discord_alert(startup_msg, 0x888888)
        print(f"\n[*] Bot running... SL: {STOP_LOSS_PERCENTAGE:.0%}, TP: {TAKE_PROFIT_PERCENTAGE:.0%}")
        print("-" * 50)
        send_status_update(address, info)
        while True:
            schedule.run_pending()
            try:
                user_state = info.user_state(address)
                positions = user_state.get("assetPositions", [])
                for pos in positions:
                    pos_info = pos["position"]
                    roe = float(pos_info["returnOnEquity"])
                    should_close, reason, alert_color = False, "", 0
                    if roe <= -STOP_LOSS_PERCENTAGE:
                        should_close, reason, alert_color = True, "STOP-LOSS", 0xff0000
                    elif roe >= TAKE_PROFIT_PERCENTAGE:
                        should_close, reason, alert_color = True, "TAKE-PROFIT", 0x00ff00
                    if should_close:
                        asset_to_close, size_to_close = pos_info["coin"], float(pos_info["szi"])
                        print(f"\n[!!] {reason} TRIGGERED for {asset_to_close}! ROE: {roe:.2%}")
                        exchange.market_open(asset_to_close, size_to_close < 0, abs(size_to_close), None, 0.01)
                        alert_emoji = "🚨" if reason == "STOP-LOSS" else "💰"
                        close_message = (f"{alert_emoji} **{reason} HIT!**\n" f"Closed **{abs(size_to_close):.4f} {asset_to_close}** @ ROE **{roe:.2%}**.")
                        send_discord_alert(close_message, alert_color)
                        print("[*] Position closed. Activating trade cooldown.")
                        last_trade_time = datetime.now()
                        time.sleep(5)
                        break
            except Exception as e:
                print(f"[!] Error during position management: {e}")
            latest_record = read_last_savant_record()
            if latest_record:
                current_trigger_armed = latest_record.get('trigger_armed')
                if current_trigger_armed is not None and current_trigger_armed != last_known_trigger_state:
                    if current_trigger_armed:
                        message = "🟡 **Trigger ARMED!** Watching for price to cross above Fib 0."
                        send_discord_alert(message, 0xffff00, savant_data=latest_record)
                    else:
                        message = "🔴 **Trigger DISARMED.** Price may have crossed reset threshold."
                        send_discord_alert(message, 0xff6347, savant_data=latest_record)
                    last_known_trigger_state = current_trigger_armed
                if latest_record.get('buy_signal') and latest_record.get('timestamp') != last_traded_signal_timestamp:
                    if last_trade_time and (datetime.now() - last_trade_time) < timedelta(minutes=TRADE_COOLDOWN_MINUTES):
                        print("[*] COOLDOWN ACTIVE: Skipping new trade signal.")
                        last_traded_signal_timestamp = latest_record.get('timestamp')
                        continue
                    print(f"\n[!] New Buy Signal Detected at {latest_record.get('timestamp')}!")
                    coin = TRADE_ASSET
                    meta, market_price = info.meta(), float(info.all_mids()[coin])
                    sz_decimals = next((asset["szDecimals"] for asset in meta["universe"] if asset["name"] == coin), 2)
                    order_size_in_asset = round(TRADE_USD_SIZE / market_price, sz_decimals)
                    send_discord_alert(f"🚀 **BUY SIGNAL!** Preparing to trade...", 0x00ff00, savant_data=latest_record)
                    order_result = exchange.market_open(coin, True, order_size_in_asset, None, 0.01)
                    log_trade(coin, latest_record, order_result, order_size_in_asset, "buy")
                    if order_result.get("status") == "ok":
                        avg_px = float(order_result['response']['data']['statuses'][0]['filled']['avgPx'])
                        send_discord_alert(f"✅ **TRADE EXECUTED!** Bought **{order_size_in_asset} {coin}** @ `${avg_px:,.2f}`.", 0x0099ff)
                        last_traded_signal_timestamp = latest_record.get('timestamp')
                        last_trade_time = datetime.now()
                    else:
                        send_discord_alert(f"❌ **TRADE FAILED!** See logs.", 0xff0000)
            time.sleep(CHECK_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        send_discord_alert(f"🛑 **{TRADE_ASSET}** trading bot stopped by user.", 0x888888)
        print("\n[*] Bot stopped by user.")
    except Exception as e:
        print(f"[!!!] CRITICAL ERROR: {e}")
        send_discord_alert(f"❌ CRITICAL BOT ERROR: {e}", 0xff0000)

if __name__ == "__main__":
    main()