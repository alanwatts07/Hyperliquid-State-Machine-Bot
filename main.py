# main.py - Tmux Process Manager for Trading Bot System (Safe Startup Edition)
#
# This script manages the startup and monitoring of the full 4-part system.
# NEW: It now checks if a process is already running and will NOT restart it.
#      It only starts processes that are not currently active.
#
# 1. collector.py (price data collection)
# 2. app.py (dashboard and signal generation)
# 3. trade_bot.py (trade execution & risk management)
# 4. discord_bot.py (Discord alerts & commands)

import subprocess
import time
import os
import sys
import signal
from datetime import datetime

# --- Configuration ---
COLLECTOR_SCRIPT = "collector.py"
DASHBOARD_SCRIPT = "app.py"
TRADE_BOT_SCRIPT = "trade_bot.py"
DISCORD_BOT_SCRIPT = "discord_bot.py"

CHECK_INTERVAL = 10  # Check process health every 10 seconds
STARTUP_DELAY = 5    # Wait 5 seconds between starting each process

# Tmux session names
TMUX_SESSIONS = {
    "Collector": "collector",
    "Dashboard": "dashboard",
    "Trade Bot": "tradebot",
    "Discord Bot": "discordbot"
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
        
    def start_tmux_process(self, script_name, process_name, session_name):
        """Start a process in a new tmux session"""
        try:
            if not os.path.exists(script_name):
                self.log(f"❌ ERROR: {script_name} not found!")
                return False
                
            self.log(f"🚀 Starting {process_name} in tmux session '{session_name}'...")
            
            cmd = ['tmux', 'new-session', '-d', '-s', session_name, sys.executable, script_name]
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

    # <-- MODIFIED: This function now checks before starting
    def start_all_processes(self):
        """Start all processes in correct order, skipping any that are already running."""
        self.log("🚀 Verifying Trading Bot System in Tmux...")
        self.log("=" * 60)
        
        processes = [
            (COLLECTOR_SCRIPT, "Collector", TMUX_SESSIONS["Collector"]),
            (DASHBOARD_SCRIPT, "Dashboard", TMUX_SESSIONS["Dashboard"]),
            (TRADE_BOT_SCRIPT, "Trade Bot", TMUX_SESSIONS["Trade Bot"]),
            (DISCORD_BOT_SCRIPT, "Discord Bot", TMUX_SESSIONS["Discord Bot"])
        ]
        
        for script, process_name, session_name in processes:
            # First, check if the session already exists
            if self.tmux_session_exists(session_name):
                self.log(f"👍 {process_name} is already running in session '{session_name}'. Skipping.")
                self.sessions[process_name] = session_name # Add to monitor list
            else:
                # If it doesn't exist, start it
                if self.start_tmux_process(script, process_name, session_name):
                    self.log(f"⏳ Waiting {STARTUP_DELAY} seconds for {process_name} to initialize...")
                    time.sleep(STARTUP_DELAY)
                else:
                    self.log(f"❌ Failed to start {process_name}. Aborting system check.")
                    return False
                
        self.log("🎉 All required processes are running successfully!")
        self.log("=" * 60)
        return True
        
    def monitor_processes(self):
        """Monitor all processes and restart if needed"""
        self.log("👀 Monitoring tmux sessions...")
        
        while self.running:
            try:
                for process_name, script, session in [("Collector", COLLECTOR_SCRIPT, TMUX_SESSIONS["Collector"]),
                                                      ("Dashboard", DASHBOARD_SCRIPT, TMUX_SESSIONS["Dashboard"]),
                                                      ("Trade Bot", TRADE_BOT_SCRIPT, TMUX_SESSIONS["Trade Bot"]), 
                                                      ("Discord Bot", DISCORD_BOT_SCRIPT, TMUX_SESSIONS["Discord Bot"])]:
                    if session not in self.sessions.values():
                         self.sessions[process_name] = session

                    if not self.tmux_session_exists(session):
                        self.log(f"⚠️  {process_name} is not running! Attempting restart...")
                        self.start_tmux_process(script, process_name, session)
                
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
        
        processes = [
            ("Collector", "🔄 Collecting price data"),
            ("Dashboard", "📈 Generating signals (app.py)"),
            ("Trade Bot", "🤖 Trade execution & risk management"),
            ("Discord Bot", "💬 Discord alerts & commands")
        ]
        
        for process_name, description in processes:
            session_name = TMUX_SESSIONS[process_name]
            if self.tmux_session_exists(session_name):
                self.log(f"✅ {process_name:<12} (tmux: {session_name:<12}) - {description}")
                self.sessions[process_name] = session_name # Ensure it's in our list
            else:
                self.log(f"❌ {process_name:<12} (STOPPED) - {description}")
                
        self.log("-" * 60)
        self.log("🎯 System is running! Press Ctrl+C to stop this manager (won't stop tmux sessions).")
        self.log("💡 To stop everything, run `python3 main.py stop`")
        self.log(f"👀 Monitoring health every {CHECK_INTERVAL} seconds...")
        self.log("")
        
        self.log("💡 TMUX COMMANDS:")
        self.log("   tmux list-sessions")
        for process_name, session_name in TMUX_SESSIONS.items():
            self.log(f"   tmux attach -t {session_name:<12} - View {process_name} output")
        self.log("   Ctrl+B then D                  - Detach from a tmux session")
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
    scripts = [COLLECTOR_SCRIPT, DASHBOARD_SCRIPT, TRADE_BOT_SCRIPT, DISCORD_BOT_SCRIPT]
    if any(not os.path.exists(s) for s in scripts):
        print("❌ Missing one or more script files. Please ensure all are present.")
        return
        
    print("✅ All script files found.")
    manager.run()

if __name__ == "__main__":
    main()