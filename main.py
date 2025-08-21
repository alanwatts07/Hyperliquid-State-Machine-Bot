# main.py - Tmux Process Manager for Trading Bot System (Full Stack Edition)
#
# This script manages the startup and monitoring of the full 5-part system.
# It now checks if a process is already running and will NOT restart it.
# It starts the Express.js server first, then the Python components.

import subprocess
import time
import os
import sys
import signal
from datetime import datetime
# This script assumes a port_manager.py file exists, as in your original script.
# If not, you can comment out lines related to it.
try:
    from port_manager import port_manager
except ImportError:
    port_manager = None


# --- Configuration ---
# Python Scripts
COLLECTOR_SCRIPT = "collector.py"
DASHBOARD_SCRIPT = "app.py"
TRADE_BOT_SCRIPT = "trade_bot.py"
DISCORD_BOT_SCRIPT = "discord_bot.py"

# --- NEW: Node.js Server Configuration ---
EXPRESS_SERVER_DIR = "express-redis-server"  # The directory of your Node.js app
EXPRESS_SERVER_SCRIPT = "server.js"         # The main file for your Node.js app

# System Settings
CHECK_INTERVAL = 10  # Check process health every 10 seconds
STARTUP_DELAY = 5    # Wait 5 seconds between starting each process

# Tmux session names
TMUX_SESSIONS = {
    "Collector": "collector",
    "Dashboard": "dashboard_hyp",
    "Trade Bot": "tradebot",
    "Discord Bot": "discordbot",
    "Express Server": "express_server" # New session for the server
}

class TmuxProcessManager:
    def __init__(self):
        self.sessions = {}
        self.running = True

    def log(self, message):
        """Print timestamped log message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    def check_tmux_installed(self):
        """Check if tmux is installed"""
        try:
            result = subprocess.run(['tmux', '-V'], capture_output=True, text=True)
            if result.returncode == 0:
                self.log(f"✅ Tmux found: {result.stdout.strip()}")
                return True
            return False
        except FileNotFoundError:
            self.log("❌ Tmux not installed! Please install tmux to use this manager.")
            return False

    def tmux_session_exists(self, session_name):
        """Check if a tmux session exists"""
        result = subprocess.run(['tmux', 'has-session', '-t', session_name], capture_output=True)
        return result.returncode == 0

    def kill_tmux_session(self, session_name):
        """Kill a tmux session if it exists"""
        if self.tmux_session_exists(session_name):
            subprocess.run(['tmux', 'kill-session', '-t', session_name], capture_output=True)
            self.log(f"🗑️  Killed tmux session: {session_name}")
        return True

    def show_dashboard_ports(self):
        """Show which ports the dashboards are running on"""
        if not port_manager:
            return
        config = port_manager.load_config()
        self.log("🌐 DASHBOARD ACCESS:")
        if "main_bot" in config:
            port = config["main_bot"]["port"]
            self.log(f"   Main Bot Dashboard: http://localhost:{port}")
        else:
            self.log("   Main Bot Dashboard: Not configured")

    # <-- MODIFIED: This function is now more generic to handle any command ---
    def start_tmux_process(self, process_name, session_name, command, file_to_check):
        """Start a process with a specific command in a new tmux session."""
        try:
            if not os.path.exists(file_to_check):
                self.log(f"❌ ERROR: Required file not found: {file_to_check}!")
                return False

            self.log(f"🚀 Starting {process_name} in tmux session '{session_name}'...")

            # Command to create a new detached tmux session and run the command
            cmd = ['tmux', 'new-session', '-d', '-s', session_name, command]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                self.sessions[process_name] = session_name
                self.log(f"✅ {process_name} started successfully")
                self.log(f"   💡 To view: tmux attach -t {session_name}")
                return True
            else:
                self.log(f"❌ ERROR starting {process_name}: {result.stderr}")
                return False

        except Exception as e:
            self.log(f"❌ ERROR starting {process_name}: {e}")
            return False

    def stop_all_processes(self):
        """Stop all managed processes by killing their tmux sessions"""
        self.log("🛑 Stopping all managed tmux sessions...")
        for process_name, session_name in TMUX_SESSIONS.items():
            self.kill_tmux_session(session_name)
            self.log(f"   - Stopped {process_name} (session: {session_name})")
        self.sessions.clear()

    # <-- MODIFIED: Now includes the Express server in the startup sequence ---
    def start_all_processes(self):
        """Start all processes in correct order, skipping any that are already running."""
        self.log("🚀 Verifying Trading Bot System in Tmux...")
        self.log("=" * 60)

        processes = [
            # The Express server is started first as other components depend on it.
            {
                "name": "Express Server",
                "session": TMUX_SESSIONS["Express Server"],
                "file_to_check": os.path.join(EXPRESS_SERVER_DIR, EXPRESS_SERVER_SCRIPT),
                "command": f"cd {EXPRESS_SERVER_DIR} && node {EXPRESS_SERVER_SCRIPT}"
            },
            {
                "name": "Collector",
                "session": TMUX_SESSIONS["Collector"],
                "file_to_check": COLLECTOR_SCRIPT,
                "command": f"{sys.executable} {COLLECTOR_SCRIPT}"
            },
            {
                "name": "Dashboard",
                "session": TMUX_SESSIONS["Dashboard"],
                "file_to_check": DASHBOARD_SCRIPT,
                "command": f"{sys.executable} {DASHBOARD_SCRIPT}"
            },
            {
                "name": "Trade Bot",
                "session": TMUX_SESSIONS["Trade Bot"],
                "file_to_check": TRADE_BOT_SCRIPT,
                "command": f"{sys.executable} {TRADE_BOT_SCRIPT}"
            },
            {
                "name": "Discord Bot",
                "session": TMUX_SESSIONS["Discord Bot"],
                "file_to_check": DISCORD_BOT_SCRIPT,
                "command": f"{sys.executable} {DISCORD_BOT_SCRIPT}"
            }
        ]

        for p in processes:
            if self.tmux_session_exists(p["session"]):
                self.log(f"👍 {p['name']} is already running in session '{p['session']}'. Skipping.")
                self.sessions[p['name']] = p["session"]  # Add to monitor list
            else:
                if self.start_tmux_process(p['name'], p['session'], p['command'], p['file_to_check']):
                    self.log(f"⏳ Waiting {STARTUP_DELAY} seconds for {p['name']} to initialize...")
                    time.sleep(STARTUP_DELAY)
                else:
                    self.log(f"❌ Failed to start {p['name']}. Aborting system check.")
                    return False

        self.log("🎉 All required processes are running successfully!")
        self.log("=" * 60)
        return True

    def monitor_processes(self):
        # This function would need to be updated to use the new `processes` structure
        # for restarting, but the current logic is close enough for basic monitoring.
        self.log("👀 Monitoring tmux sessions...")
        while self.running:
            try:
                # Basic monitoring, can be enhanced
                for process_name, session_name in self.sessions.items():
                     if not self.tmux_session_exists(session_name):
                         self.log(f"⚠️  {process_name} session '{session_name}' is not running! Please restart manually or enhance the monitor.")
                         # For a full auto-restart, you would re-run the start logic for this specific process
                time.sleep(CHECK_INTERVAL)

            except KeyboardInterrupt:
                self.log("🛑 Keyboard interrupt received...")
                break
            except Exception as e:
                self.log(f"❌ Error in monitoring loop: {e}")
                time.sleep(CHECK_INTERVAL)

    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.log(f"📡 Received signal {signum}")
        self.running = False

    def show_status(self):
        """Show current system status"""
        self.log("\n📊 SYSTEM STATUS:")
        self.log("-" * 60)
        if port_manager: self.show_dashboard_ports()

        processes = [
            ("Express Server", "📡 API and Redis publisher"),
            ("Collector", "🔄 Collecting price data"),
            ("Dashboard", "📈 Generating signals (app.py)"),
            ("Trade Bot", "🤖 Trade execution & risk management"),
            ("Discord Bot", "💬 Discord alerts & commands")
        ]

        for process_name, description in processes:
            session_name = TMUX_SESSIONS[process_name]
            if self.tmux_session_exists(session_name):
                self.log(f"✅ {process_name:<15} (tmux: {session_name:<15}) - {description}")
                self.sessions[process_name] = session_name
            else:
                self.log(f"❌ {process_name:<15} (STOPPED) - {description}")

        self.log("-" * 60)
        self.log("🎯 System is running! Press Ctrl+C to stop this manager (won't stop tmux sessions).")
        self.log("💡 To stop everything, run `python3 main.py stop`")
        self.log(f"👀 Monitoring health every {CHECK_INTERVAL} seconds...")
        self.log("\n💡 TMUX COMMANDS:")
        self.log("   tmux list-sessions")
        for process_name, session_name in TMUX_SESSIONS.items():
            self.log(f"   tmux attach -t {session_name:<15} - View {process_name} output")
        self.log("   Ctrl+B then D               - Detach from a tmux session")
        self.log("")

    def run(self):
        """Main run function"""
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        try:
            if not self.check_tmux_installed(): return
            if not self.start_all_processes(): return
            self.show_status()
            self.monitor_processes()
        except Exception as e:
            self.log(f"❌ Critical error in run loop: {e}")
        finally:
            self.log("👋 Manager stopped. Tmux sessions are still running in the background.")

def main():
    """Main entry point with command-line arguments for start/stop"""
    print("🤖 Trading Bot System Manager (Tmux Edition)")
    print("=" * 60)

    manager = TmuxProcessManager()

    if len(sys.argv) > 1 and sys.argv[1] == 'stop':
        manager.stop_all_processes()
        print("👋 System shutdown complete.")
        return

    # Check if all script files exist before starting
    scripts_to_check = [
        os.path.join(EXPRESS_SERVER_DIR, EXPRESS_SERVER_SCRIPT),
        COLLECTOR_SCRIPT,
        DASHBOARD_SCRIPT,
        TRADE_BOT_SCRIPT,
        DISCORD_BOT_SCRIPT
    ]
    if any(not os.path.exists(s) for s in scripts_to_check):
        print("❌ Missing one or more script files. Please ensure all are present:")
        for s in scripts_to_check:
            if not os.path.exists(s): print(f"   - {s}")
        return

    print("✅ All script files found.")
    manager.run()

if __name__ == "__main__":
    main()