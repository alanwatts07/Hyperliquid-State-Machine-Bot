import json
import requests
import time
from datetime import datetime, timedelta, timezone

# --- Configuration ---
CONFIG_FILE = "config.json"
# <-- NEW: Specify the exact webhook name to target
WEBHOOK_NAME_TO_DELETE = "Trade-sigs" 

def load_config():
    """Loads the main config.json file."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[!!!] CRITICAL: `{CONFIG_FILE}` not found. Please create it.")
        return None
    except json.JSONDecodeError:
        print(f"[!!!] CRITICAL: Could not decode `{CONFIG_FILE}`. Check for syntax errors.")
        return None

def discord_api_request(bot_token, endpoint, method="POST", payload=None):
    """A helper function to make authenticated requests to the Discord API."""
    if not bot_token: return None
    headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}
    url = f"https://discord.com/api/v10{endpoint}"
    try:
        if method == "POST": response = requests.post(url, headers=headers, json=payload, timeout=10)
        elif method == "GET": response = requests.get(url, headers=headers, params=payload, timeout=10)
        elif method == "DELETE": response = requests.delete(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json() if response.status_code != 204 else None
    except requests.exceptions.RequestException as e:
        print(f"[!] Discord API Error on endpoint {endpoint}: {e}")
        if e.response: print(f"    Response: {e.response.text}")
        return None

def purge_channel():
    """Fetches and deletes messages from a specific webhook in the configured channel."""
    config = load_config()
    if not config: return

    bot_token = config.get("discord_bot_token")
    channel_id = config.get("discord_channel_id")
    if not bot_token or not channel_id:
        print("[!!!] `discord_bot_token` or `discord_channel_id` not found in config.json.")
        return
        
    print("--- Channel Cleanup Utility ---")
    print(f"[*] Targeting messages from webhook: '{WEBHOOK_NAME_TO_DELETE}'")
    print(f"[*] Fetching messages from channel {channel_id}...")

    messages_to_delete = []
    two_weeks_ago = datetime.now(timezone.utc) - timedelta(days=14)
    last_message_id = None
    
    while True:
        payload = {"limit": 100}
        if last_message_id:
            payload['before'] = last_message_id
            
        messages = discord_api_request(bot_token, f"/channels/{channel_id}/messages", method="GET", payload=payload)
        
        if not messages:
            break
            
        # <-- MODIFIED: This now filters by both author name and age
        webhook_messages = [
            msg for msg in messages
            if msg['author']['username'] == WEBHOOK_NAME_TO_DELETE 
            and datetime.fromisoformat(msg['timestamp']) > two_weeks_ago
        ]
        
        if webhook_messages:
            messages_to_delete.extend(webhook_messages)
        
        if len(messages) < 100:
            break # Reached the end of the channel history
            
        print(f"[*] Found {len(messages_to_delete)} matching messages so far...")
        last_message_id = messages[-1]['id']
        time.sleep(1) # Be respectful to the API rate limits

    if not messages_to_delete:
        print(f"🟢 No messages from '{WEBHOOK_NAME_TO_DELETE}' found to delete (or all are older than 14 days).")
        return

    delete_ids = [msg['id'] for msg in messages_to_delete]
    
    print("="*50)
    print(f"Found {len(delete_ids)} messages from '{WEBHOOK_NAME_TO_DELETE}' to delete.")
    print("This action is IRREVERSIBLE.")
    
    try:
        confirm = input("❓ Are you sure you want to proceed? (y/n): ").lower().strip()
    except KeyboardInterrupt:
        print("\n🛑 Operation cancelled.")
        return

    if confirm == 'y':
        print("[*] Deleting messages in batches...")
        for i in range(0, len(delete_ids), 100):
            batch_ids = delete_ids[i:i+100]
            if len(batch_ids) > 1:
                payload = {"messages": batch_ids}
                discord_api_request(bot_token, f"/channels/{channel_id}/messages/bulk-delete", payload=payload)
            elif len(batch_ids) == 1:
                 discord_api_request(bot_token, f"/channels/{channel_id}/messages/{batch_ids[0]}", method="DELETE")
            print(f"[*] Deleted batch of {len(batch_ids)} messages.")
            time.sleep(2)
            
        print("✅ Cleanup complete!")
    else:
        print("🛑 Deletion cancelled.")

if __name__ == "__main__":
    purge_channel()