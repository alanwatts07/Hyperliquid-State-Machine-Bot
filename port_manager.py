# port_manager.py - Centralized Port Management
import json
import os
import socket
import time
from datetime import datetime

class PortManager:
    def __init__(self, config_file="port_assignments.json"):
        self.config_file = config_file
        self.base_ports = {
            "main_bot": 8050,
            "jupiter_bot": 8051,
            "main_bot_backup": 8052,
            "jupiter_bot_backup": 8053
        }
        
    def is_port_free(self, port):
        """Check if a port is actually free"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                result = sock.bind(('localhost', port))
                return True
        except OSError:
            return False
    
    def get_free_port(self, bot_name, start_port=None):
        """Get a free port for the specified bot"""
        if start_port is None:
            start_port = self.base_ports.get(bot_name, 8050)
        
        # Try the preferred port first
        if self.is_port_free(start_port):
            return start_port
        
        # Try backup port
        backup_port = start_port + 10
        if self.is_port_free(backup_port):
            return backup_port
        
        # Find any free port in range
        for port in range(start_port + 1, start_port + 50):
            if self.is_port_free(port):
                return port
        
        raise Exception(f"No free ports found for {bot_name}")
    
    def reserve_port(self, bot_name):
        """Reserve a port for a bot and save to config"""
        config = self.load_config()
        
        # Check if bot already has a reserved port that's still free
        if bot_name in config:
            existing_port = config[bot_name]["port"]
            if self.is_port_free(existing_port):
                return existing_port
        
        # Get a new free port
        start_port = self.base_ports.get(bot_name, 8050)
        new_port = self.get_free_port(bot_name, start_port)
        
        # Save reservation
        config[bot_name] = {
            "port": new_port,
            "reserved_at": datetime.now().isoformat(),
            "pid": os.getpid()
        }
        
        self.save_config(config)
        return new_port
    
    def release_port(self, bot_name):
        """Release a port reservation"""
        config = self.load_config()
        if bot_name in config:
            del config[bot_name]
            self.save_config(config)
    
    def load_config(self):
        """Load port configuration"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}
    
    def save_config(self, config):
        """Save port configuration"""
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
    
    def cleanup_stale_reservations(self):
        """Clean up reservations from dead processes"""
        config = self.load_config()
        active_config = {}
        
        for bot_name, info in config.items():
            port = info["port"]
            if not self.is_port_free(port):  # Port still in use
                active_config[bot_name] = info
        
        self.save_config(active_config)

# Global instance
port_manager = PortManager()