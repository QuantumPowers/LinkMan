"""
LinkMan VPN GUI application.

Provides a cross-platform graphical interface for LinkMan VPN client.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import threading
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

from linkman.client.main import LinkManClient
from linkman.shared.utils.logger import get_logger, add_gui_log_handler, remove_gui_log_handler
from linkman.shared.utils.config import Config, load_config, save_config

logger = get_logger("client.gui")


class LinkManGUI:
    """
    LinkMan VPN GUI application.
    """
    
    def __init__(self, root: tk.Tk):
        """
        Initialize the GUI application.
        
        Args:
            root: Tkinter root window
        """
        self.root = root
        self.root.title("LinkMan VPN")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # Set window icon if available
        # self._set_icon()
        
        self.client: Optional[LinkManClient] = None
        self.config: Optional[Config] = None
        self.config_path: Optional[Path] = None
        self.is_running = False
        
        # Create main notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create tabs
        self._create_config_tab()
        self._create_status_tab()
        self._create_log_tab()
        self._create_about_tab()
        
        # Create menu bar
        self._create_menu()
        
        # Create status bar
        self._create_status_bar()
        
        # Add log handler
        add_gui_log_handler(self._add_log_message)
        
        # Load configuration
        self._load_config()
        
        # Set up close handler
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _set_icon(self):
        """
        Set window icon.
        """
        # TODO: Add icon file
        pass
    
    def _create_menu(self):
        """
        Create menu bar.
        """
        menubar = tk.Menu(self.root)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load Config", command=self._load_config_dialog)
        file_menu.add_command(label="Save Config", command=self._save_config_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Preferences", command=self._open_preferences)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Help", command=self._show_help)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.root.config(menu=menubar)
    
    def _create_status_bar(self):
        """
        Create status bar.
        """
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        
        status_bar = ttk.Label(
            self.root,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def _create_config_tab(self):
        """
        Create configuration tab.
        """
        config_frame = ttk.Frame(self.notebook)
        self.notebook.add(config_frame, text="Configuration")
        
        # Create notebook for config sections
        config_notebook = ttk.Notebook(config_frame)
        config_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Client config
        client_frame = ttk.Frame(config_notebook)
        config_notebook.add(client_frame, text="Client")
        
        # Server config
        server_frame = ttk.Frame(config_notebook)
        config_notebook.add(server_frame, text="Server")
        
        # Crypto config
        crypto_frame = ttk.Frame(config_notebook)
        config_notebook.add(crypto_frame, text="Crypto")
        
        # TLS config
        tls_frame = ttk.Frame(config_notebook)
        config_notebook.add(tls_frame, text="TLS")
        
        # Client config widgets
        ttk.Label(client_frame, text="Local Host:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        self.local_host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(client_frame, textvariable=self.local_host_var, width=30).grid(row=0, column=1, padx=10, pady=5)
        
        ttk.Label(client_frame, text="Local Port:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        self.local_port_var = tk.StringVar(value="1080")
        ttk.Entry(client_frame, textvariable=self.local_port_var, width=10).grid(row=1, column=1, padx=10, pady=5)
        
        # Server config widgets
        ttk.Label(server_frame, text="Server Host:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        self.server_host_var = tk.StringVar(value="")
        ttk.Entry(server_frame, textvariable=self.server_host_var, width=30).grid(row=0, column=1, padx=10, pady=5)
        
        ttk.Label(server_frame, text="Server Port:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        self.server_port_var = tk.StringVar(value="8388")
        ttk.Entry(server_frame, textvariable=self.server_port_var, width=10).grid(row=1, column=1, padx=10, pady=5)
        
        # Crypto config widgets
        ttk.Label(crypto_frame, text="Master Key:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        self.master_key_var = tk.StringVar(value="")
        ttk.Entry(crypto_frame, textvariable=self.master_key_var, width=50, show="*").grid(row=0, column=1, padx=10, pady=5)
        
        ttk.Label(crypto_frame, text="Cipher:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        self.cipher_var = tk.StringVar(value="aes-256-gcm")
        cipher_values = ["aes-256-gcm", "chacha20-poly1305"]
        ttk.Combobox(crypto_frame, textvariable=self.cipher_var, values=cipher_values, width=20).grid(row=1, column=1, padx=10, pady=5)
        
        # Protocol config
        ttk.Label(crypto_frame, text="Protocol:").grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
        self.protocol_var = tk.StringVar(value="shadowsocks2022")
        protocol_values = ["shadowsocks2022"]  # Add more protocols here as they are implemented
        ttk.Combobox(crypto_frame, textvariable=self.protocol_var, values=protocol_values, width=20).grid(row=2, column=1, padx=10, pady=5)
        
        # TLS config widgets
        ttk.Label(tls_frame, text="Enabled:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        self.tls_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tls_frame, variable=self.tls_enabled_var).grid(row=0, column=1, padx=10, pady=5, sticky=tk.W)
        
        ttk.Label(tls_frame, text="WebSocket Enabled:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        self.websocket_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tls_frame, variable=self.websocket_enabled_var).grid(row=1, column=1, padx=10, pady=5, sticky=tk.W)
        
        ttk.Label(tls_frame, text="WebSocket Path:").grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
        self.websocket_path_var = tk.StringVar(value="/linkman")
        ttk.Entry(tls_frame, textvariable=self.websocket_path_var, width=30).grid(row=2, column=1, padx=10, pady=5)
        
        # Save button
        ttk.Button(config_frame, text="Save Configuration", command=self._save_config).pack(pady=10)
    
    def _create_status_tab(self):
        """
        Create status tab.
        """
        status_frame = ttk.Frame(self.notebook)
        self.notebook.add(status_frame, text="Status")
        
        # Connection status
        status_top = ttk.Frame(status_frame)
        status_top.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(status_top, text="Connection Status:", font=('Helvetica', 12, 'bold')).pack(anchor=tk.W)
        
        self.status_text = tk.Text(status_top, height=10, width=70)
        self.status_text.pack(fill=tk.BOTH, expand=True, pady=5)
        self.status_text.insert(tk.END, "Not connected\n")
        self.status_text.config(state=tk.DISABLED)
        
        # Traffic statistics
        stats_frame = ttk.Frame(status_frame)
        stats_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(stats_frame, text="Traffic Statistics:", font=('Helvetica', 12, 'bold')).pack(anchor=tk.W)
        
        stats_grid = ttk.Frame(stats_frame)
        stats_grid.pack(fill=tk.X, pady=5)
        
        ttk.Label(stats_grid, text="Bytes Sent:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        self.bytes_sent_var = tk.StringVar(value="0")
        ttk.Label(stats_grid, textvariable=self.bytes_sent_var).grid(row=0, column=1, sticky=tk.W, padx=10, pady=5)
        
        ttk.Label(stats_grid, text="Bytes Received:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        self.bytes_received_var = tk.StringVar(value="0")
        ttk.Label(stats_grid, textvariable=self.bytes_received_var).grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)
        
        # Control buttons
        control_frame = ttk.Frame(status_frame)
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.connect_button = ttk.Button(control_frame, text="Connect", command=self._connect)
        self.connect_button.pack(side=tk.LEFT, padx=5)
        
        self.disconnect_button = ttk.Button(control_frame, text="Disconnect", command=self._disconnect, state=tk.DISABLED)
        self.disconnect_button.pack(side=tk.LEFT, padx=5)
        
        self.refresh_button = ttk.Button(control_frame, text="Refresh", command=self._refresh_status)
        self.refresh_button.pack(side=tk.LEFT, padx=5)
    
    def _create_log_tab(self):
        """
        Create log tab.
        """
        log_frame = ttk.Frame(self.notebook)
        self.notebook.add(log_frame, text="Logs")
        
        # Log text widget
        self.log_text = tk.Text(log_frame, height=20, width=80)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.log_text.config(state=tk.DISABLED)
        
        # Clear button
        ttk.Button(log_frame, text="Clear Logs", command=self._clear_logs).pack(side=tk.RIGHT, padx=10, pady=5)
    
    def _create_about_tab(self):
        """
        Create about tab.
        """
        about_frame = ttk.Frame(self.notebook)
        self.notebook.add(about_frame, text="About")
        
        about_text = """LinkMan VPN

Version: 1.0.0

A high-performance, secure VPN implementation based on Shadowsocks 2022 protocol.

Features:
- High Performance: Optimized async IO and buffer management
- Secure: AEAD encryption
- Flexible: Multiple protocols and transport methods
- Reliable: Connection pooling and health checking
- Monitorable: Comprehensive metrics collection
- Extensible: Modular architecture

© 2026 LinkMan VPN"""
        
        ttk.Label(about_frame, text=about_text, justify=tk.LEFT).pack(padx=20, pady=20)
    
    def _load_config(self, path: Optional[Path] = None):
        """
        Load configuration from file.
        
        Args:
            path: Optional config file path
        """
        if path is None:
            # Default config path
            config_dir = Path.home() / ".linkman"
            config_dir.mkdir(exist_ok=True)
            path = config_dir / "client_config.json"
        
        self.config_path = path
        
        try:
            if path.exists():
                self.config = load_config(path)
                self._update_config_widgets()
                self.status_var.set(f"Loaded config from {path}")
            else:
                # Create default config
                self.config = Config()
                self.status_var.set(f"Created default config")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            messagebox.showerror("Error", f"Failed to load config: {e}")
    
    def _load_config_dialog(self):
        """
        Open file dialog to load config.
        """
        from tkinter import filedialog
        
        path = filedialog.askopenfilename(
            title="Load Configuration",
            filetypes=[("JSON files", "*.json"), ("All files", "*")]
        )
        
        if path:
            self._load_config(Path(path))
    
    def _save_config(self, path: Optional[Path] = None):
        """
        Save configuration to file.
        
        Args:
            path: Optional config file path
        """
        if self.config is None:
            self.config = Config()
        
        if path is None:
            path = self.config_path
            if path is None:
                # Default config path
                config_dir = Path.home() / ".linkman"
                config_dir.mkdir(exist_ok=True)
                path = config_dir / "client_config.json"
        
        try:
            # Update config from widgets
            self._update_config_from_widgets()
            
            # Save config
            save_config(self.config, path)
            self.config_path = path
            self.status_var.set(f"Saved config to {path}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            messagebox.showerror("Error", f"Failed to save config: {e}")
    
    def _save_config_dialog(self):
        """
        Open file dialog to save config.
        """
        from tkinter import filedialog
        
        path = filedialog.asksaveasfilename(
            title="Save Configuration",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*")]
        )
        
        if path:
            self._save_config(Path(path))
    
    def _update_config_widgets(self):
        """
        Update config widgets from config object.
        """
        if self.config is None:
            return
        
        # Client config
        self.local_host_var.set(self.config.client.local_host)
        self.local_port_var.set(str(self.config.client.local_port))
        
        # Server config
        self.server_host_var.set(self.config.client.server_host)
        self.server_port_var.set(str(self.config.client.server_port))
        
        # Crypto config
        self.master_key_var.set(self.config.crypto.key)
        self.cipher_var.set(self.config.crypto.cipher)
        
        # Protocol config
        if hasattr(self.config, 'protocol'):
            self.protocol_var.set(self.config.protocol)
        
        # TLS config
        self.tls_enabled_var.set(self.config.tls.enabled)
        self.websocket_enabled_var.set(self.config.tls.websocket_enabled)
        self.websocket_path_var.set(self.config.tls.websocket_path)
    
    def _update_config_from_widgets(self):
        """
        Update config object from widgets.
        """
        if self.config is None:
            self.config = Config()
        
        # Client config
        self.config.client.local_host = self.local_host_var.get()
        try:
            self.config.client.local_port = int(self.local_port_var.get())
        except ValueError:
            pass
        
        # Server config
        self.config.client.server_host = self.server_host_var.get()
        try:
            self.config.client.server_port = int(self.server_port_var.get())
        except ValueError:
            pass
        
        # Crypto config
        self.config.crypto.key = self.master_key_var.get()
        self.config.crypto.cipher = self.cipher_var.get()
        
        # Protocol config
        if not hasattr(self.config, 'protocol'):
            self.config.protocol = "shadowsocks2022"
        self.config.protocol = self.protocol_var.get()
        
        # TLS config
        self.config.tls.enabled = self.tls_enabled_var.get()
        self.config.tls.websocket_enabled = self.websocket_enabled_var.get()
        self.config.tls.websocket_path = self.websocket_path_var.get()
    
    def _connect(self):
        """
        Connect to VPN server.
        """
        if self.is_running:
            messagebox.showinfo("Info", "Already connected")
            return
        
        try:
            # Save config
            self._save_config()
            
            # Create client
            self.client = LinkManClient()
            
            # Start client in a separate thread
            self.is_running = True
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.status_var.set("Connecting...")
            
            def start_client():
                asyncio.run(self.client.start())
            
            thread = threading.Thread(target=start_client, daemon=True)
            thread.start()
            
            # Update status
            self._update_status()
        except Exception as e:
            logger.error(f"Error connecting: {e}")
            messagebox.showerror("Error", f"Failed to connect: {e}")
            self.is_running = False
            self.connect_button.config(state=tk.NORMAL)
            self.disconnect_button.config(state=tk.DISABLED)
    
    def _disconnect(self):
        """
        Disconnect from VPN server.
        """
        if not self.is_running:
            messagebox.showinfo("Info", "Not connected")
            return
        
        try:
            if self.client:
                asyncio.run(self.client.stop())
            
            self.is_running = False
            self.connect_button.config(state=tk.NORMAL)
            self.disconnect_button.config(state=tk.DISABLED)
            self.status_var.set("Disconnected")
            self._update_status()
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
            messagebox.showerror("Error", f"Failed to disconnect: {e}")
    
    def _refresh_status(self):
        """
        Refresh status display.
        """
        self._update_status()
    
    def _update_status(self):
        """
        Update status display.
        """
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete(1.0, tk.END)
        
        if self.is_running and self.client:
            status = "Connected"
            self.status_text.insert(tk.END, f"Status: {status}\n")
            self.status_text.insert(tk.END, f"Server: {self.config.client.server_host}:{self.config.client.server_port}\n")
            self.status_text.insert(tk.END, f"Local: {self.config.client.local_host}:{self.config.client.local_port}\n")
            
            # Update traffic stats
            if hasattr(self.client, "_proxy") and self.client._proxy:
                bytes_sent = getattr(self.client._proxy, "_bytes_sent", 0)
                bytes_received = getattr(self.client._proxy, "_bytes_received", 0)
                self.bytes_sent_var.set(f"{bytes_sent}")
                self.bytes_received_var.set(f"{bytes_received}")
        else:
            status = "Not connected"
            self.status_text.insert(tk.END, f"Status: {status}\n")
            self.bytes_sent_var.set("0")
            self.bytes_received_var.set("0")
        
        self.status_text.config(state=tk.DISABLED)
    
    def _add_log_message(self, message: str, level: str):
        """
        Add log message to log widget.
        
        Args:
            message: Log message
            level: Log level
        """
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{level}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def _clear_logs(self):
        """
        Clear log widget.
        """
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def _open_preferences(self):
        """
        Open preferences dialog.
        """
        messagebox.showinfo("Preferences", "Preferences not implemented yet")
    
    def _show_help(self):
        """
        Show help dialog.
        """
        help_text = """LinkMan VPN Help

1. Configuration:
   - Enter server details in the Configuration tab
   - Save the configuration

2. Connection:
   - Click Connect to start the VPN
   - Click Disconnect to stop the VPN

3. Status:
   - View connection status and traffic statistics

4. Logs:
   - View application logs

For more information, visit the documentation."""
        messagebox.showinfo("Help", help_text)
    
    def _show_about(self):
        """
        Show about dialog.
        """
        about_text = """LinkMan VPN

Version: 1.0.0

A high-performance, secure VPN implementation based on Shadowsocks 2022 protocol.

© 2026 LinkMan VPN"""
        messagebox.showinfo("About", about_text)
    
    def _on_close(self):
        """
        Handle window close event.
        """
        if self.is_running:
            if messagebox.askyesno("Confirm", "Are you sure you want to disconnect and exit?"):
                self._disconnect()
        
        # Remove log handler
        remove_gui_log_handler(self._add_log_message)
        
        self.root.destroy()


def main():
    """
    Main function for GUI application.
    """
    root = tk.Tk()
    app = LinkManGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
