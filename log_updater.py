import json
import os

# --- Configuration ---
LOG_FILE = "trade_log.json"

def update_trade_logs():
    """
    Reads the trade log file and adds 'trade_type': 'buy' to any
    entries that are missing this field (for backward compatibility).
    """
    print(f"[*] Checking log file for updates: {LOG_FILE}")

    # Check if the file exists
    if not os.path.exists(LOG_FILE):
        print(f"[!] Error: Log file '{LOG_FILE}' not found. Nothing to update.")
        return

    try:
        # Read the existing log data
        with open(LOG_FILE, 'r') as f:
            logs = json.load(f)

        if not isinstance(logs, list):
            print("[!] Error: Log file is not in the expected format (a list of trades).")
            return

        updated_count = 0
        # Iterate through each log entry
        for entry in logs:
            # Check if 'trade_type' key is missing
            if 'trade_type' not in entry:
                entry['trade_type'] = 'buy'
                updated_count += 1
        
        if updated_count > 0:
            # Write the updated log data back to the file
            with open(LOG_FILE, 'w') as f:
                json.dump(logs, f, indent=4)
            print(f"✅ Success! Updated {updated_count} log entries and saved the file.")
        else:
            print("[*] No entries needed updating. File is already in the correct format.")

    except json.JSONDecodeError:
        print(f"[!] Error: Could not decode JSON from '{LOG_FILE}'. Please check the file for corruption.")
    except Exception as e:
        print(f"[!] An unexpected error occurred: {e}")

if __name__ == "__main__":
    update_trade_logs()
