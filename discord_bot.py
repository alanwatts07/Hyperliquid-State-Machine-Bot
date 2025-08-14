# discord_bot.py
import discord
from discord.ext import tasks, commands
import json
import os # <-- Import os
from datetime import datetime
from db_manager import DatabaseManager

# --- Load Configuration ---
try:
    with open("config.json", 'r') as f:
        config = json.load(f)
    BOT_TOKEN = config.get("discord_bot_token")
    CHANNEL_ID = int(config.get("discord_channel_id"))
    TRADE_ASSET = "SOL"
    PRICE_SAVANT_FILE = "price_savant.json" # <-- Add savant file path
except (FileNotFoundError, json.JSONDecodeError, TypeError):
    print("[!!!] CRITICAL: `config.json` is missing, corrupt, or doesn't contain required keys.")
    exit()

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
db = DatabaseManager()

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

# --- Main Status Reporting Task ---
@tasks.loop(minutes=15)
async def send_status_report():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("[!] Channel not found. Cannot send status report.")
        return

    # Get fresh data for the report
    position = db.get_open_position(TRADE_ASSET)
    savant_data = read_last_savant_record()

    # Create the detailed embed
    embed = discord.Embed(
        title=f"✅ 15-Minute Status Report",
        description="Bot is alive and monitoring.",
        color=0x3498db,
        timestamp=datetime.now()
    )

    # Add open position details if a position exists
    if position:
        pnl = 0.0
        # Calculate live PnL if we have savant data
        if savant_data and savant_data.get('price'):
            current_price = float(savant_data.get('price', 0))
            pnl = (current_price - position['entry_px']) * position['size']
        
        pnl_emoji = "🔼" if pnl >= 0 else "🔽"
        pnl_str = f"${pnl:,.2f}"
        
        field_value = (
            f"**`{position['direction']} {position['size']:.4f} {position['asset']}`**\n"
            f"**Entry:** `${position['entry_px']:,.2f}`\n"
            f"**Est. Live PnL:** `{pnl_emoji} {pnl_str}`"
        )
        embed.add_field(name=f"📊 Open Position: {position['asset']}", value=field_value, inline=False)
    else:
        embed.description += "\nNo open positions."

    # Add detailed savant data if it's available
    if savant_data:
        embed.add_field(name="Price", value=f"`${savant_data.get('price', 0):.3f}`", inline=True)
        embed.add_field(name="Trigger Armed", value=f"**`{savant_data.get('trigger_armed', 'N/A')}`**", inline=True)
        embed.add_field(name="Buy Signal", value=f"**`{savant_data.get('buy_signal', 'N/A')}`**", inline=True)
        embed.add_field(name="Fib Entry", value=f"`${savant_data.get('fib_entry', 0):.3f}`", inline=True)
        embed.add_field(name="Fib 0", value=f"`${savant_data.get('wma_fib_0', 0):.3f}`", inline=True)
        embed.add_field(name="ATR", value=f"`{savant_data.get('atr', 0):.4f}`", inline=True)
        embed.add_field(name="Timestamp", value=f"`{savant_data.get('timestamp')}`", inline=False)
    
    await channel.send(embed=embed)

# --- Bot Events ---
@bot.event
async def on_ready():
    print(f"--- Discord Bot Connected ---")
    print(f"[*] Logged in as: {bot.user.name}")
    print(f"[*] Monitoring database for events...")
    send_status_report.start()

# --- Bot Commands ---
@bot.command()
async def status(ctx):
    """Provides an instant status update."""
    if ctx.channel.id != CHANNEL_ID: return
    # We can reuse the main task function to send an instant report
    await ctx.send("Fetching instant status report...")
    await send_status_report()

# --- Run the Bot ---
bot.run(BOT_TOKEN)