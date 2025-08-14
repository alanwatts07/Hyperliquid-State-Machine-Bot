# discord_bot.py
import discord
from discord.ext import tasks, commands
import json
import os
from datetime import datetime
from db_manager import DatabaseManager

# --- Load Configuration ---
try:
    with open("config.json", 'r') as f:
        config = json.load(f)
    BOT_TOKEN = config.get("discord_bot_token")
    CHANNEL_ID = int(config.get("discord_channel_id"))
    TRADE_ASSET = "SOL"
    PRICE_SAVANT_FILE = "price_savant.json"
except (FileNotFoundError, json.JSONDecodeError, TypeError):
    print("[!!!] CRITICAL: `config.json` is missing, corrupt, or doesn't contain required keys.")
    exit()

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
db = DatabaseManager()
last_processed_event_id = 0 # State tracker for the event loop

# --- Helper to Read Savant File ---
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

def format_event_details(event_type, details):
    """Translates raw event data into a pretty, human-readable string."""
    try:
        if event_type in ["TRIGGER_ARMED", "TRIGGER_DISARMED", "BUY_SIGNAL"]:
            price = details.get("savant_data", {}).get("price", 0)
            return f"Market price was ${price:.3f}"
        
        elif event_type == "TRADE_EXECUTED":
            asset, size, avg_px = details.get('asset'), details.get('size'), details.get('avg_px')
            return f"Bought {size:.4f} {asset} @ ${avg_px:,.2f}"
            
        elif event_type in ["STOP-LOSS_HIT", "TAKE-PROFIT_HIT"]:
            asset, size, roe = details.get('asset'), details.get('size'), details.get('roe')
            return f"Closed {size:.4f} {asset} @ {roe:.2%} ROE"

        elif event_type == "COMMAND_EXECUTED":
            command = details.get("command")
            count = details.get("closed_count", 0)
            return f"Command '{command}' executed, closed {count} position(s)."

        elif event_type in ["BOT_STARTED", "BOT_STOPPED"]:
            return details.get("message", "No details.")
        
        else:
            # Fallback for any other event types
            details_str = json.dumps(details)
            return (details_str[:200] + '...') if len(details_str) > 200 else details_str
            
    except Exception:
        return "Could not parse details."
# --- Background Tasks ---

@tasks.loop(seconds=10)
async def check_for_events():
    """Polls the database for new events and sends real-time alerts."""
    global last_processed_event_id
    channel = bot.get_channel(CHANNEL_ID)
    if not channel: return

    # Check for new events since the last processed one
    db.cursor.execute("SELECT id, event_type, details FROM events WHERE id > ? ORDER BY id ASC", (last_processed_event_id,))
    new_events = db.cursor.fetchall()

    for event_id, event_type, details_json in new_events:
        details = json.loads(details_json)
        savant_data = details.get("savant_data")
        
        embed = discord.Embed(timestamp=datetime.now())
        
        # Format embed based on event type
        if event_type == "TRIGGER_ARMED":
            embed.title = "🟡 Trigger ARMED!"
            embed.description = "Watching for price to cross above Fib 0."
            embed.color = 0xffff00
        elif event_type == "TRIGGER_DISARMED":
            embed.title = "🔴 Trigger DISARMED"
            embed.description = "Price may have crossed reset threshold."
            embed.color = 0xff6347
        elif event_type == "BUY_SIGNAL":
            embed.title = "🚀 BUY SIGNAL!"
            embed.description = "Signal detected. Trading bot is executing trade..."
            embed.color = 0x00ff00
        elif event_type == "TRADE_EXECUTED":
            asset, size, avg_px = details.get('asset'), details.get('size'), details.get('avg_px')
            embed.title = f"✅ TRADE EXECUTED!"
            embed.description = f"Bought **{size:.4f} {asset}** @ `${avg_px:,.2f}`."
            embed.color = 0x0099ff
        elif event_type == "STOP-LOSS_HIT":
            asset, size, roe = details.get('asset'), details.get('size'), details.get('roe')
            embed.title = f"🚨 STOP-LOSS TRIGGERED!"
            embed.description = f"Closed **{size:.4f} {asset}** position @ **{roe:.2%}** ROE."
            embed.color = 0xff0000
        elif event_type == "TAKE-PROFIT_HIT":
            asset, size, roe = details.get('asset'), details.get('size'), details.get('roe')
            embed.title = f"💰 TAKE PROFIT HIT!"
            embed.description = f"Closed **{size:.4f} {asset}** position @ **{roe:.2%}** ROE."
            embed.color = 0x00ff00
        else:
            continue # Skip other event types for real-time alerts

        if savant_data:
            embed.add_field(name="Price", value=f"`${savant_data.get('price', 0):.3f}`", inline=True)
            embed.add_field(name="Trigger Armed", value=f"**`{savant_data.get('trigger_armed', 'N/A')}`**", inline=True)
            embed.add_field(name="Buy Signal", value=f"**`{savant_data.get('buy_signal', 'N/A')}`**", inline=True)

        await channel.send(embed=embed)
        last_processed_event_id = event_id # Update state

@tasks.loop(minutes=15)
async def send_status_report():
    """Sends the detailed, scheduled status report."""
    channel = bot.get_channel(CHANNEL_ID)
    if not channel: return

    position = db.get_open_position(TRADE_ASSET)
    savant_data = read_last_savant_record()
    last_event = db.get_last_event()
    embed = discord.Embed(title=f"✅ 15-Minute Status Report", description="Bot is alive and monitoring.", color=0x3498db, timestamp=datetime.now())
    if last_event:
        event_time = datetime.fromisoformat(last_event['timestamp']).strftime('%H:%M:%S')
        embed.set_footer(text=f"Last Event: {last_event['event_type']} at {event_time}")
    if position:
        pnl = 0.0
        if savant_data and savant_data.get('price'):
            pnl = (float(savant_data.get('price', 0)) - position['entry_px']) * position['size']
        pnl_emoji, pnl_str = ("🔼", f"${pnl:,.2f}") if pnl >= 0 else ("🔽", f"${pnl:,.2f}")
        field_value = (f"**`{position['direction']} {position['size']:.4f} {position['asset']}`**\n" f"**Entry:** `${position['entry_px']:,.2f}`\n" f"**Est. Live PnL:** `{pnl_emoji} {pnl_str}`")
        embed.add_field(name=f"📊 Open Position: {position['asset']}", value=field_value, inline=False)
    else:
        embed.description += "\nNo open positions."
    if savant_data:
        embed.add_field(name="Price", value=f"`${savant_data.get('price', 0):.3f}`", inline=True)
        embed.add_field(name="Trigger Armed", value=f"**`{savant_data.get('trigger_armed', 'N/A')}`**", inline=True)
        embed.add_field(name="Buy Signal", value=f"**`{savant_data.get('buy_signal', 'N/A')}`**", inline=True)
        embed.add_field(name="Fib Entry", value=f"`${savant_data.get('fib_entry', 0):.3f}`", inline=True)
        embed.add_field(name="Fib 0", value=f"`${savant_data.get('wma_fib_0', 0):.3f}`", inline=True)
        embed.add_field(name="ATR", value=f"`{savant_data.get('atr', 0):.4f}`", inline=True)
        embed.add_field(name="Timestamp", value=f"`{savant_data.get('timestamp')}`", inline=False)
    await channel.send(embed=embed)

# --- Bot Events & Commands ---
@bot.event
async def on_ready():
    global last_processed_event_id
    print(f"--- Discord Bot Connected ---")
    print(f"[*] Logged in as: {bot.user.name}")
    db.cursor.execute("SELECT id FROM events ORDER BY id DESC LIMIT 1")
    last_event = db.cursor.fetchone()
    if last_event: last_processed_event_id = last_event[0]
    print(f"[*] Starting event checks from ID: {last_processed_event_id}")
    check_for_events.start()
    send_status_report.start()

@bot.command()
async def status(ctx):
    """Provides an instant status update."""
    if ctx.channel.id != CHANNEL_ID: return
    await ctx.send("Fetching instant status report...")
    await send_status_report()

@bot.command(name='panic')
@commands.is_owner()
async def panic(ctx):
    """Signals the trading bot to prepare to close all positions."""
    position = db.get_open_position(TRADE_ASSET)
    if not position:
        await ctx.send("There are no open positions to close.")
        return
    db.set_command("CLOSE_ALL", "PENDING")
    embed = discord.Embed(title="🚨 Panic Close Initiated", description="Review the position below and confirm.", color=0xffa500)
    field_value = (f"**`{position['direction']} {position['size']:.4f} {position['asset']}`**\n" f"**Entry:** `${position['entry_px']:,.2f}`")
    embed.add_field(name=f"Position to Close", value=field_value, inline=False)
    embed.set_footer(text="Type !confirm_close to execute.")
    await ctx.send(embed=embed)

@bot.command(name='confirm_close')
@commands.is_owner()
async def confirm_close(ctx):
    """Confirms and executes the closing of all positions."""
    if db.get_command("CLOSE_ALL") == "PENDING":
        db.set_command("CLOSE_ALL", "CONFIRMED")
        await ctx.send("✅ **Confirmation received!** Signal sent to the trading bot to close all positions.")
    else:
        await ctx.send("⚠️ No pending close command found. Please run `!panic` first.")

@bot.command(name='logs')

async def logs(ctx, limit: int = 10):
    """Fetches and displays the last N events from the bot's database."""
    if limit > 25: limit = 25
        
    await ctx.send(f"📜 Fetching the last {limit} bot events...")
    
    events = db.get_latest_events(limit)
    
    if not events:
        await ctx.send("No events found in the database.")
        return
        
    embed = discord.Embed(
        title="📜 Recent Bot Events",
        color=0x7289DA # Discord Blurple
    )
    
    description = ""
    for event in reversed(events): # Reverse to show oldest first
        ts = datetime.fromisoformat(event['timestamp']).strftime('%H:%M:%S')
        event_type = event['event_type']
        
        # Use the new formatter function here
        details_str = format_event_details(event_type, event['details'])
            
        description += f"`{ts}` **{event_type}**\n` > ` {details_str}\n"
    
    embed.description = description
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        await ctx.send("⚠️ You do not have permission to use this command.")
    else:
        print(f"An unhandled command error occurred: {error}")

# --- Run the Bot ---
bot.run(BOT_TOKEN)