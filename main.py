# main.py - Tmux Process Manager for Trading Bot System
#
# This script manages the startup and monitoring of:
# 1. collector.py (price data collection) - in tmux session "collector"
# 2. app.py (dashboard and signal generation) - in tmux session "dashboard"
# 3. trade_bot.py (trade execution with alerts) - in tmux session "tradebot"
#
# Usage: python main.py

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

CHECK_INTERVAL = 10  # Check process health every 10 seconds
STARTUP_DELAY = 5    # Wait 5 seconds between starting each process

# Tmux session names
TMUX_SESSIONS = {
    "Collector": "collector",
    "Dashboard": "dashboard", 
    "Trade Bot": "tradebot"
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
            else:
                self.log("❌ Tmux not found!")
                return False
        except FileNotFoundError:
            self.log("❌ Tmux not installed! Please install tmux:")
            self.log("   Ubuntu/Debian: sudo apt install tmux")
            self.log("   macOS: brew install tmux")
            self.log("   Or run without tmux using the basic version")
            return False
            
    def tmux_session_exists(self, session_name):
        """Check if a tmux session exists"""
        try:
            result = subprocess.run(['tmux', 'has-session', '-t', session_name], 
                                   capture_output=True)
            return result.returncode == 0
        except:
            return False
            
    def kill_tmux_session(self, session_name):
        """Kill a tmux session if it exists"""
        if self.tmux_session_exists(session_name):
            try:
                subprocess.run(['tmux', 'kill-session', '-t', session_name], 
                              capture_output=True)
                self.log(f"🗑️  Killed existing tmux session: {session_name}")
                return True
            except:
                return False
        return True
        
    def start_tmux_process(self, script_name, process_name, session_name):
        """Start a process in a new tmux session"""
        try:
            if not os.path.exists(script_name):
                self.log(f"❌ ERROR: {script_name} not found!")
                return False
                
            # Kill existing session if it exists
            self.kill_tmux_session(session_name)
            
            self.log(f"🚀 Starting {process_name} in tmux session '{session_name}'...")
            
            # Create new tmux session and run the script
            cmd = [
                'tmux', 'new-session', '-d', '-s', session_name,
                sys.executable, script_name
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.sessions[process_name] = session_name
                self.log(f"✅ {process_name} started in tmux session '{session_name}'")
                self.log(f"   💡 To view: tmux attach -t {session_name}")
                return True
            else:
                self.log(f"❌ ERROR starting {process_name}: {result.stderr}")
                return False
                
        except Exception as e:
            self.log(f"❌ ERROR starting {process_name}: {e}")
            return False
            
    def is_tmux_session_running(self, session_name):
        """Check if a tmux session is still running"""
        return self.tmux_session_exists(session_name)
        
    def is_process_running(self, process_name):
        """Check if a process is still running in its tmux session"""
        if process_name not in self.sessions:
            return False
            
        session_name = self.sessions[process_name]
        if self.is_tmux_session_running(session_name):
            return True
        else:
            self.log(f"❌ {process_name} tmux session '{session_name}' has stopped")
            return False
            
    def stop_process(self, process_name):
        """Stop a process by killing its tmux session"""
        if process_name not in self.sessions:
            return
            
        session_name = self.sessions[process_name]
        if self.kill_tmux_session(session_name):
            self.log(f"🛑 Stopped {process_name} (session: {session_name})")
        
        del self.sessions[process_name]
        
    def stop_all_processes(self):
        """Stop all managed processes"""
        self.log("🛑 Stopping all tmux sessions...")
        for process_name in list(self.sessions.keys()):
            self.stop_process(process_name)
            
    def start_all_processes(self):
        """Start all processes in correct order"""
        self.log("🚀 Starting Trading Bot System in Tmux...")
        self.log("=" * 60)
        
        processes = [
            (COLLECTOR_SCRIPT, "Collector", TMUX_SESSIONS["Collector"]),
            (DASHBOARD_SCRIPT, "Dashboard", TMUX_SESSIONS["Dashboard"]),
            (TRADE_BOT_SCRIPT, "Trade Bot", TMUX_SESSIONS["Trade Bot"])
        ]
        
        for script, process_name, session_name in processes:
            if self.start_tmux_process(script, process_name, session_name):
                self.log(f"⏳ Waiting {STARTUP_DELAY} seconds for {process_name} to initialize...")
                time.sleep(STARTUP_DELAY)
            else:
                self.log(f"❌ Failed to start {process_name}. Aborting startup.")
                return False
                
        self.log("🎉 All processes started successfully in tmux!")
        self.log("=" * 60)
        return True
        
    def monitor_processes(self):
        """Monitor all processes and restart if needed"""
        self.log("👀 Monitoring tmux sessions...")
        
        while self.running:
            try:
                # Check each process
                for process_name in ["Collector", "Dashboard", "Trade Bot"]:
                    if not self.is_process_running(process_name):
                        self.log(f"⚠️  {process_name} is not running! Attempting restart...")
                        
                        # Restart based on process type
                        if process_name == "Collector":
                            self.start_tmux_process(COLLECTOR_SCRIPT, "Collector", TMUX_SESSIONS["Collector"])
                        elif process_name == "Dashboard":
                            self.start_tmux_process(DASHBOARD_SCRIPT, "Dashboard", TMUX_SESSIONS["Dashboard"])
                        elif process_name == "Trade Bot":
                            self.start_tmux_process(TRADE_BOT_SCRIPT, "Trade Bot", TMUX_SESSIONS["Trade Bot"])
                
                # Wait before next check
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
        self.log("-" * 50)
        
        processes = [
            ("Collector", COLLECTOR_SCRIPT, "🔄 Collecting price data"),
            ("Dashboard", DASHBOARD_SCRIPT, "📊 Dashboard & signals"), 
            ("Trade Bot", TRADE_BOT_SCRIPT, "🤖 Trade execution & alerts")
        ]
        
        for process_name, script, description in processes:
            if self.is_process_running(process_name):
                session_name = self.sessions[process_name]
                self.log(f"✅ {process_name:<12} (tmux: {session_name:<10}) - {description}")
            else:
                self.log(f"❌ {process_name:<12} (STOPPED) - {description}")
                
        self.log("-" * 50)
        self.log("🎯 System is running in tmux! Press Ctrl+C to stop all processes.")
        self.log(f"👀 Monitoring health every {CHECK_INTERVAL} seconds...")
        self.log("")
        
        # Show tmux commands
        self.log("💡 TMUX COMMANDS:")
        self.log("   tmux list-sessions          - List all sessions")
        self.log("   tmux attach -t collector     - View collector output")  
        self.log("   tmux attach -t dashboard     - View dashboard output")
        self.log("   tmux attach -t tradebot      - View trade bot output")
        self.log("   Ctrl+B then D               - Detach from tmux session")
        self.log("")
        
    def run(self):
        """Main run function"""
        # Set up signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        try:
            # Check tmux
            if not self.check_tmux_installed():
                return
                
            # Start all processes
            if not self.start_all_processes():
                self.log("❌ Failed to start system. Exiting.")
                return
                
            # Show status
            self.show_status()
            
            # Monitor processes
            self.monitor_processes()
            
        except Exception as e:
            self.log(f"❌ Critical error: {e}")
        finally:
            # Clean shutdown
            self.stop_all_processes()
            self.log("👋 Trading Bot System shutdown complete.")

def main():
    """Main entry point"""
    print("🤖 Trading Bot System Manager (Tmux Edition)")
    print("=" * 60)
    
    # Check if we're in a virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("✅ Virtual environment detected")
    else:
        print("⚠️  Warning: No virtual environment detected")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("👋 Exiting. Activate your virtual environment and try again.")
            return
    
    # Check if all script files exist
    scripts = [COLLECTOR_SCRIPT, DASHBOARD_SCRIPT, TRADE_BOT_SCRIPT]
    missing_scripts = [script for script in scripts if not os.path.exists(script)]
    
    if missing_scripts:
        print(f"❌ Missing script files: {', '.join(missing_scripts)}")
        print("   Make sure all scripts are in the current directory.")
        return
        
    print("✅ All script files found")
    print("")
    
    # Start the process manager
    manager = TmuxProcessManager()
    manager.run()

if __name__ == "__main__":
    main()