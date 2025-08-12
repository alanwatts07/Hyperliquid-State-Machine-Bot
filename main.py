# main.py - Process Manager for Trading Bot System
#
# This script manages the startup and monitoring of:
# 1. collector.py (price data collection)
# 2. app.py (dashboard and signal generation) 
# 3. trade_bot.py (trade execution with alerts)
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
TRADE_BOT_SCRIPT = "trade_bot.py"  # Assuming your trade file is named this

CHECK_INTERVAL = 10  # Check process health every 10 seconds
STARTUP_DELAY = 5    # Wait 5 seconds between starting each process

class ProcessManager:
    def __init__(self):
        self.processes = {}
        self.running = True
        
    def log(self, message):
        """Print timestamped log message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        
    def is_process_running(self, process_name):
        """Check if a process is still running"""
        if process_name not in self.processes:
            return False
            
        process = self.processes[process_name]
        if process.poll() is None:
            return True
        else:
            self.log(f"❌ {process_name} has stopped (exit code: {process.returncode})")
            return False
            
    def start_process(self, script_name, process_name):
        """Start a Python process"""
        try:
            if not os.path.exists(script_name):
                self.log(f"❌ ERROR: {script_name} not found!")
                return False
                
            self.log(f"🚀 Starting {process_name}...")
            
            # Start the process
            process = subprocess.Popen([
                sys.executable, script_name
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
               bufsize=1, universal_newlines=True)
            
            self.processes[process_name] = process
            self.log(f"✅ {process_name} started (PID: {process.pid})")
            return True
            
        except Exception as e:
            self.log(f"❌ ERROR starting {process_name}: {e}")
            return False
            
    def stop_process(self, process_name):
        """Stop a process gracefully"""
        if process_name not in self.processes:
            return
            
        process = self.processes[process_name]
        if process.poll() is None:  # Process is still running
            self.log(f"🛑 Stopping {process_name}...")
            process.terminate()
            
            # Wait up to 10 seconds for graceful shutdown
            try:
                process.wait(timeout=10)
                self.log(f"✅ {process_name} stopped gracefully")
            except subprocess.TimeoutExpired:
                self.log(f"⚠️  Force killing {process_name}...")
                process.kill()
                process.wait()
                self.log(f"💀 {process_name} force killed")
                
        del self.processes[process_name]
        
    def stop_all_processes(self):
        """Stop all managed processes"""
        self.log("🛑 Stopping all processes...")
        for process_name in list(self.processes.keys()):
            self.stop_process(process_name)
            
    def start_all_processes(self):
        """Start all processes in correct order"""
        self.log("🚀 Starting Trading Bot System...")
        self.log("=" * 50)
        
        # 1. Start collector first (data collection)
        if self.start_process(COLLECTOR_SCRIPT, "Collector"):
            self.log(f"⏳ Waiting {STARTUP_DELAY} seconds for collector to initialize...")
            time.sleep(STARTUP_DELAY)
        else:
            self.log("❌ Failed to start collector. Aborting startup.")
            return False
            
        # 2. Start dashboard (signal generation)
        if self.start_process(DASHBOARD_SCRIPT, "Dashboard"):
            self.log(f"⏳ Waiting {STARTUP_DELAY} seconds for dashboard to initialize...")
            time.sleep(STARTUP_DELAY)
        else:
            self.log("❌ Failed to start dashboard. Aborting startup.")
            return False
            
        # 3. Start trade bot (trade execution)
        if self.start_process(TRADE_BOT_SCRIPT, "Trade Bot"):
            self.log(f"⏳ Waiting {STARTUP_DELAY} seconds for trade bot to initialize...")
            time.sleep(STARTUP_DELAY)
        else:
            self.log("❌ Failed to start trade bot. Aborting startup.")
            return False
            
        self.log("🎉 All processes started successfully!")
        self.log("=" * 50)
        return True
        
    def monitor_processes(self):
        """Monitor all processes and restart if needed"""
        self.log("👀 Monitoring processes...")
        
        while self.running:
            try:
                # Check each process
                for process_name in ["Collector", "Dashboard", "Trade Bot"]:
                    if not self.is_process_running(process_name):
                        self.log(f"⚠️  {process_name} is not running! Attempting restart...")
                        
                        # Restart based on process type
                        if process_name == "Collector":
                            self.start_process(COLLECTOR_SCRIPT, "Collector")
                        elif process_name == "Dashboard":
                            self.start_process(DASHBOARD_SCRIPT, "Dashboard")
                        elif process_name == "Trade Bot":
                            self.start_process(TRADE_BOT_SCRIPT, "Trade Bot")
                
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
        
    def run(self):
        """Main run function"""
        # Set up signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        try:
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
            
    def show_status(self):
        """Show current system status"""
        self.log("\n📊 SYSTEM STATUS:")
        self.log("-" * 30)
        
        processes = [
            ("Collector", COLLECTOR_SCRIPT, "🔄 Collecting price data"),
            ("Dashboard", DASHBOARD_SCRIPT, "📊 Dashboard & signals"), 
            ("Trade Bot", TRADE_BOT_SCRIPT, "🤖 Trade execution & alerts")
        ]
        
        for process_name, script, description in processes:
            if self.is_process_running(process_name):
                pid = self.processes[process_name].pid
                self.log(f"✅ {process_name:<12} (PID: {pid:<6}) - {description}")
            else:
                self.log(f"❌ {process_name:<12} (STOPPED) - {description}")
                
        self.log("-" * 30)
        self.log("🎯 System is running! Press Ctrl+C to stop all processes.")
        self.log(f"👀 Monitoring health every {CHECK_INTERVAL} seconds...")
        self.log("")

def main():
    """Main entry point"""
    print("🤖 Trading Bot System Manager")
    print("=" * 50)
    
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
    manager = ProcessManager()
    manager.run()

if __name__ == "__main__":
    main()