# discord_bot.py (Corrected with Non-Blocking API Calls)
import discord
from discord.ext import commands, tasks
import json
import os
import redis
import asyncio # <-- Required for running tasks in the background
from datetime import datetime, timedelta

# --- Hyperliquid API Integration ---
from hyperliquid.info import Info
from hyperliquid.utils import constants
import example_utils 

# --- Configuration ---
CONFIG_FILE = "config.json"
PRICE_SAVANT_FILE = "price_savant.json"
CHECK_INTERVAL_SECONDS = 3 

# --- Bot & Trading Globals (Loaded from Config) ---
config = None
OWNER_ID = None
USER_ADDRESS = None
TRADE_ASSET = "SOL" 
TRADE_USD_SIZE = 625
TRADE_COOLDOWN_MINUTES = 10
STOP_LOSS_PERCENTAGE = 0.0045
TAKE_PROFIT_PERCENTAGE = 0.0215
TRAILING_ACTIVATION_PERCENTAGE = 0.0050
TRAILING_STOP_DISTANCE = 0.0025

# --- API & State Tracking ---
info_api = None
exchange_api = None
redis_client = None
position_peaks = {}
last_trade_time = None
last_traded_signal_timestamp = None

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command('help')

# --- Helper & API Functions ---
# (Your helper functions like load_config, read_last_savant_record, get_live_positions, manage_risk, etc. remain the same)
def load_config():
    """Loads all settings from the config.json file."""
    global config, OWNER_ID, USER_ADDRESS, TRADE_ASSET, TRADE_USD_SIZE, TRADE_COOLDOWN_MINUTES, STOP_LOSS_PERCENTAGE, TAKE_PROFIT_PERCENTAGE, TRAILING_ACTIVATION_PERCENTAGE, TRAILING_STOP_DISTANCE
    try:
        with open(CONFIG_FILE, 'r') as f:
            cfg = json.load(f)
            config = cfg; OWNER_ID = cfg.get("owner_id"); USER_ADDRESS = cfg.get("hyperliquid_wallet_address")
            TRADE_ASSET = cfg.get("trade_asset", "SOL")
            TRADE_USD_SIZE = cfg.get("trade_usd_size", 625)
            TRADE_COOLDOWN_MINUTES = cfg.get("trade_cooldown_minutes", 10)
            STOP_LOSS_PERCENTAGE = cfg.get("stop_loss_percentage", 0.0045)
            TAKE_PROFIT_PERCENTAGE = cfg.get("take_profit_percentage", 0.0215)
            TRAILING_ACTIVATION_PERCENTAGE = cfg.get("trailing_activation_percentage", 0.0050)
            TRAILING_STOP_DISTANCE = cfg.get("trailing_stop_distance", 0.0025)
            return cfg
    except Exception as e:
        print(f"[!!!] CRITICAL: Could not load `{CONFIG_FILE}`. Error: {e}"); return None

def read_last_savant_record():
    """Reads the last signal data record from the savant file."""
    if not os.path.exists(PRICE_SAVANT_FILE): return None
    try:
        with open(PRICE_SAVANT_FILE, 'rb') as f:
            f.seek(-4096, os.SEEK_END)
            buffer = f.read().decode('utf-8', errors='ignore')
            last_obj_start = buffer.rfind('{')
            return json.loads(buffer[last_obj_start:]) if last_obj_start != -1 else None
    except: return None

def get_live_positions(user_state):
    """Processes a user_state snapshot to find all open positions."""
    if not user_state: return []
    processed = []
    for p in user_state.get("assetPositions", []):
        if float(p["position"]["szi"]) != 0:
            pos = p['position']; size = float(pos['szi'])
            processed.append({
                "asset": pos['coin'], "direction": "LONG" if size > 0 else "SHORT",
                "size": abs(size), "entry_px": float(pos['entryPx']),
                "pnl": float(pos['unrealizedPnl']), "leverage": float(pos['leverage']['value']),
                "roe": float(pos['returnOnEquity'])
            })
    return processed

def manage_risk(position):
    """Calculates and updates risk levels for a position."""
    global position_peaks
    asset = position['asset']
    current_roe = position['roe']

    if asset not in position_peaks:
        position_peaks[asset] = {'peak_roe': current_roe, 'trailing_active': False, 'stop_level': -STOP_LOSS_PERCENTAGE}

    peak_data = position_peaks[asset]
    if current_roe > peak_data['peak_roe']:
        peak_data['peak_roe'] = current_roe
        if current_roe >= TRAILING_ACTIVATION_PERCENTAGE and not peak_data['trailing_active']:
            peak_data['trailing_active'] = True
        if peak_data['trailing_active']:
            new_stop_level = current_roe - TRAILING_STOP_DISTANCE
            if new_stop_level > peak_data['stop_level']: peak_data['stop_level'] = new_stop_level
    
    if current_roe >= TAKE_PROFIT_PERCENTAGE: return True, f"TAKE-PROFIT at {current_roe:.2%}"
    if current_roe <= peak_data['stop_level']:
        return True, "TRAILING-STOP" if peak_data['trailing_active'] else "STOP-LOSS"
    return False, None
    
# --- THE ONLY STATUS FUNCTION YOU NEED ---
async def send_unified_status_embed(channel, title):
    loop = asyncio.get_running_loop()
    # Run blocking API calls in a background thread
    user_state = await asyncio.to_thread(info_api.user_state, USER_ADDRESS) if info_api and USER_ADDRESS else None
    
    savant_data = read_last_savant_record()
    live_positions = get_live_positions(user_state)

    embed = discord.Embed(title=title, color=0x2ECC71, timestamp=datetime.now())
    embed.set_footer(text="Hyperliquid State-Aware Bot")

    if savant_data:
        embed.add_field(name="Price", value=f"`${savant_data.get('price', 0):.4f}`", inline=True)
        embed.add_field(name="Trigger Armed", value=f"**`{savant_data.get('trigger_armed', 'N/A')}`**", inline=True)
        embed.add_field(name="Buy Signal", value=f"**`{savant_data.get('buy_signal', 'N/A')}`**", inline=True)
        embed.add_field(name="Fib Entry", value=f"`${savant_data.get('fib_entry', 0):.4f}`", inline=True)
        embed.add_field(name="Fib 0", value=f"`${savant_data.get('wma_fib_0', 0):.4f}`", inline=True)
        embed.add_field(name="ATR", value=f"`{savant_data.get('atr', 0):.4f}`", inline=True)
    else:
        embed.description = "Signal data is not yet available."

    if not live_positions:
        embed.add_field(name="📊 Live Positions", value="No open positions found.", inline=False)
    else:
        embed.add_field(name="\u200b", value="--- **Live Positions** ---", inline=False)
        for pos in live_positions:
            pnl_emoji = "🔼" if pos['pnl'] >= 0 else "🔽"
            field_name = f"{pos['direction']} {pos['size']:.4f} {pos['asset']} ({pos['leverage']:.0f}x)"
            field_value = f"**Entry:** `${pos['entry_px']:,.4f}`\n**PnL:** `{pnl_emoji} ${pos['pnl']:,.2f}`"
            embed.add_field(name=field_name, value=field_value, inline=True)
            if pos['asset'] == TRADE_ASSET:
                manage_risk(pos) 
                if TRADE_ASSET in position_peaks:
                    risk_data = position_peaks[TRADE_ASSET]
                    stop_level_pct = risk_data['stop_level']
                    tp_level_pct = TAKE_PROFIT_PERCENTAGE
                    stop_type = "Trailing Stop" if risk_data['trailing_active'] else "Stop-Loss"
                    embed.add_field(name=f"🛡️ Risk Levels ({TRADE_ASSET})",
                                    value=f"**{stop_type}:** `{stop_level_pct:.2%}`\n**Take-Profit:** `{tp_level_pct:.2%}`",
                                    inline=True)
    await channel.send(embed=embed)


# --- Bot Events & Main Loop ---
@bot.event
async def on_ready():
    global config, info_api, exchange_api, redis_client
    print(f"[*] Bot logged in as {bot.user}")
    config = load_config()
    if not config or not USER_ADDRESS:
        print("[!!!] CRITICAL: Bot cannot start. Check config.json."); return
    try:
        found_address, info, exchange = example_utils.setup(constants.MAINNET_API_URL, skip_ws=True)
        info_api, exchange_api = info, exchange
        if found_address.lower() != USER_ADDRESS.lower():
            print(f"[!!!] FATAL MISMATCH: Config address ({USER_ADDRESS}) != SDK address ({found_address})."); return
        print(f"[*] Hyperliquid API connected for wallet: {found_address}")
        
        redis_client = redis.Redis(decode_responses=True)
        # Ping the server to ensure a connection is established
        redis_client.ping()
        print("[*] Redis server connection successful.")
        
        trade_and_monitor.start()
    except redis.exceptions.ConnectionError as e:
        print(f"[!!!] CRITICAL: Could not connect to Redis server. Is it running? Error: {e}")
    except Exception as e:
        print(f"[!!!] FAILED to setup APIs: {e}")

@bot.command(name='status')
async def status_command(ctx):
    thinking_message = await ctx.send("⏳ *Fetching live status...*")
    await send_unified_status_embed(ctx.channel, f"✅ {TRADE_ASSET} Instant Status Report")
    await thinking_message.delete()


@tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
async def trade_and_monitor():
    global last_trade_time, position_peaks, last_traded_signal_timestamp
    
    # --- THIS IS THE FIX ---
    # Get the current asyncio event loop
    loop = asyncio.get_running_loop()

    try:
        # Run all blocking I/O operations in a background thread
        # This prevents the bot from freezing or getting a "heartbeat blocked" error
        user_state = await asyncio.to_thread(info_api.user_state, USER_ADDRESS)
        all_mids = await asyncio.to_thread(info_api.all_mids)
        
        live_positions = get_live_positions(user_state)
        managed_position = next((p for p in live_positions if p["asset"] == TRADE_ASSET), None)

        if managed_position:
            should_close, reason = manage_risk(managed_position)
            if should_close:
                channel = bot.get_channel(config.get("discord_channel_id"))
                await channel.send(f"🔴 **Closing Position!**\n**Reason:** {reason}")
                
                raw_pos = next(p for p in user_state['assetPositions'] if p['position']['coin'] == TRADE_ASSET)
                size_to_close = float(raw_pos['position']['szi'])
                
                await asyncio.to_thread(exchange_api.market_open, TRADE_ASSET, size_to_close < 0, abs(size_to_close), None, 0.01)
                position_peaks.pop(TRADE_ASSET, None)
                last_trade_time = datetime.now()
        
        else:
            if TRADE_ASSET in position_peaks:
                position_peaks.pop(TRADE_ASSET, None)

            # Check for a message from Redis in a non-blocking way
            p = redis_client.pubsub(ignore_subscribe_messages=True)
            p.subscribe('trading-signals')
            message = await asyncio.to_thread(p.get_message) 

            if message:
                latest_record = json.loads(message['data'])
                if latest_record.get('state', {}).get('buy_signal') and latest_record.get('timestamp') != last_traded_signal_timestamp:
                    if last_trade_time and (datetime.now() - last_trade_time) < timedelta(minutes=TRADE_COOLDOWN_MINUTES):
                        print("[*] COOLDOWN ACTIVE: Skipping signal.")
                        last_traded_signal_timestamp = latest_record.get('timestamp')
                    else:
                        print(f"\n[!] New Redis Buy Signal Detected! Executing trade...")
                        channel = bot.get_channel(config.get("discord_channel_id"))
                        await channel.send(f"🚀 **Executing New Buy Signal for {TRADE_ASSET}!**")

                        market_price = float(all_mids[TRADE_ASSET])
                        meta = await asyncio.to_thread(info_api.meta)
                        sz_decimals = next((asset["szDecimals"] for asset in meta["universe"] if asset["name"] == TRADE_ASSET), 2)
                        order_size_in_asset = round(TRADE_USD_SIZE / market_price, sz_decimals)
                        
                        order_result = await asyncio.to_thread(exchange_api.market_open, TRADE_ASSET, True, order_size_in_asset, None, 0.01)

                        if order_result.get("status") == "ok":
                            avg_px = float(order_result['response']['data']['statuses'][0]['filled']['avgPx'])
                            await channel.send(f"✅ **Trade Executed:** Bought {order_size_in_asset} {TRADE_ASSET} @ `${avg_px:,.2f}`")
                            last_trade_time = datetime.now()
                            last_traded_signal_timestamp = latest_record.get('timestamp')
                        else:
                            await channel.send(f"❌ **Trade Failed!** Reason: `{order_result}`")
                            
    except Exception as e:
        print(f"❌ ERROR in main monitor loop: {e}")

@trade_and_monitor.before_loop
async def before_main_loop():
    await bot.wait_until_ready()

# --- Run the Bot ---
if __name__ == "__main__":
    if not load_config(): exit(1)
    bot_token = config.get("discord_bot_token")
    if not bot_token:
        print("[!!!] discord_bot_token not found in config.json"); exit(1)
    bot.run(bot_token)