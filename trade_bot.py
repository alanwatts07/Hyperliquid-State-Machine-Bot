# Hyperliquid All-in-One Trading & Monitoring Bot with Stop-Loss
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
CHECK_INTERVAL_SECONDS = 5  # Check every 5 seconds
TRADE_USD_SIZE = 625
TRADE_ASSET = "SOL"
TRADE_COOLDOWN_MINUTES = 10
STATUS_UPDATE_MINUTES = 15
STOP_LOSS_PERCENTAGE = 0.15  # <-- NEW: 15% stop-loss (0.15)

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

# --- CORE BOT FUNCTIONS ---
# (Functions get_open_positions, send_discord_alert, send_status_update, etc., are unchanged)
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
                {"name": "Buy Signal", "value": f"**`{savant_data.get('buy_signal', 'N/A')}`**", "inline": True},
                {"name": "Trigger Armed", "value": f"**`{savant_data.get('trigger_armed', 'N/A')}`**", "inline": True},
            ])
        if open_positions:
            for pos in open_positions:
                pnl_emoji = "🔼" if pos['pnl'] >= 0 else "🔽"
                pnl_str = f"${pos['pnl']:,.2f}"
                field_value = (f"**`{pos['direction']} {pos['size']:.4f} {pos['asset']}`**\n" f"**Entry:** `${pos['entry_px']:,.2f}`\n" f"**PnL:** `{pnl_emoji} {pnl_str}`\n" f"**Age:** `{pos['time_open']}`")
                fields.append({"name": f"📊 Open Position: {pos['asset']}", "value": field_value, "inline": False})
        if fields: embed["fields"] = fields
        requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)
    except Exception: pass
def send_status_update(address, info):
    print(f"[*] Sending {STATUS_UPDATE_MINUTES}-minute status update...")
    trade_log = load_trade_log()
    positions = get_open_positions(address, info, trade_log)
    message = f"✅ **{STATUS_UPDATE_MINUTES}-Minute Status Report.** Bot is alive and monitoring."
    if not positions: message += "\n\nNo open positions."
    send_discord_alert(message, 0x3498db, open_positions=positions)
def read_last_savant_record():
    if not os.path.exists(PRICE_SAVANT_FILE): return None
    try:
        with open(PRICE_SAVANT_FILE, 'rb') as f:
            f.seek(0, os.SEEK_END)
            if f.tell() == 0: return None
            buffer_size = 4096
            seek_pos = max(0, f.tell() - buffer_size)
            f.seek(seek_pos)
            buffer = f.read().decode('utf-8', errors='ignore')
            last_obj_start = buffer.rfind('{')
            if last_obj_start == -1: return None
            return json.loads(buffer[last_obj_start:])
    except: return None
def log_trade(coin, trigger_data, order_result, order_size, trade_type):
    log_entry = {
        "log_timestamp": datetime.now().isoformat(), "coin": coin, "trade_type": trade_type,
        "trade_size_usd": TRADE_USD_SIZE, "calculated_asset_size": order_size,
        "trigger_data": trigger_data, "exchange_response": order_result
    }
    try:
        logs = load_trade_log()
        logs.append(log_entry)
        with open(TRADE_LOG_FILE, 'w') as f: json.dump(logs, f, indent=4)
    except Exception as e: print(f"[!] CRITICAL Error logging trade: {e}")

# --- MAIN EXECUTION ---
def main():
    global last_traded_signal_timestamp, last_known_trigger_state, last_trade_time
    try:
        print("--- Hyperliquid Bot w/ Stop-Loss ---")
        address, info, exchange = example_utils.setup(constants.MAINNET_API_URL, skip_ws=True)
        print(f"[*] Wallet: {address}")
        
        schedule.every(STATUS_UPDATE_MINUTES).minutes.do(send_status_update, address=address, info=info)
        
        send_discord_alert(f"🤖 **Bot Started.** Monitoring **{TRADE_ASSET}** with a **{STOP_LOSS_PERCENTAGE:.0%} Stop-Loss**.", 0x888888)
        print(f"\n[*] Bot running... Stop-Loss: {STOP_LOSS_PERCENTAGE:.0%}")
        print("-" * 50)

        while True:
            schedule.run_pending()

            # <-- NEW SECTION: Stop-Loss Management
            try:
                user_state = info.user_state(address)
                positions = user_state.get("assetPositions", [])
                for pos in positions:
                    pos_info = pos["position"]
                    roe = float(pos_info["returnOnEquity"])
                    
                    if roe <= -STOP_LOSS_PERCENTAGE:
                        asset_to_close = pos_info["coin"]
                        size_to_close = float(pos_info["szi"])
                        
                        print("\n" + "="*50)
                        print(f"[!!] STOP-LOSS TRIGGERED for {asset_to_close}!")
                        print(f"[!!] Current ROE: {roe:.2%} | Threshold: {-STOP_LOSS_PERCENTAGE:.0%}")
                        
                        # Execute the closing order
                        is_buy_to_close = size_to_close < 0 # If size is negative (SHORT), we BUY to close
                        exchange.market_open(asset_to_close, is_buy_to_close, abs(size_to_close), None, 0.01)
                        
                        # Send alert and start cooldown
                        sl_message = (
                            f"🚨 **STOP-LOSS TRIGGERED!**\n"
                            f"Closed **{abs(size_to_close):.4f} {asset_to_close}** position due to "
                            f"reaching **{roe:.2%}** return on equity."
                        )
                        send_discord_alert(sl_message, 0xff0000)
                        
                        print("[*] Position closed. Activating trade cooldown.")
                        last_trade_time = datetime.now() # Activate cooldown to prevent immediate re-entry
                        
                        # Wait a moment to ensure the next loop sees the updated state
                        time.sleep(5)
                        break # Exit the stop-loss check loop for this iteration
            except Exception as e:
                print(f"[!] Error during stop-loss check: {e}")
            # --- End of Stop-Loss Section ---


            # --- Trade Entry Logic ---
            latest_record = read_last_savant_record()
            if latest_record and latest_record.get('buy_signal') and latest_record.get('timestamp') != last_traded_signal_timestamp:
                if last_trade_time and (datetime.now() - last_trade_time) < timedelta(minutes=TRADE_COOLDOWN_MINUTES):
                    print("[*] COOLDOWN ACTIVE: Skipping new trade signal.")
                    last_traded_signal_timestamp = latest_record.get('timestamp')
                    continue 

                print(f"\n[!] New Buy Signal Detected at {latest_record.get('timestamp')}!")
                # (The rest of your trade entry logic remains the same)
                coin = TRADE_ASSET
                meta = info.meta()
                sz_decimals = next((asset["szDecimals"] for asset in meta["universe"] if asset["name"] == coin), 2)
                market_price = float(info.all_mids()[coin])
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