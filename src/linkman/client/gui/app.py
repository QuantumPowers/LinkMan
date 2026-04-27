"""
LinkMan VPN GUI application.

Provides a cross-platform graphical interface for LinkMan VPN client.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Any

from linkman.client.main import Client
from linkman.client.utils.asyncio_manager import AsyncioManager
from linkman.client.utils.thread_safe_state import ThreadSafeState
from linkman.shared.utils.logger import get_logger, add_gui_log_handler, remove_gui_log_handler
from linkman.shared.utils.config import Config

logger = get_logger("client.gui")

DEFAULT_CONFIG_DIR = Path.home() / ".linkman"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "client_config.toml"


class LinkManGUI:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("LinkMan VPN")
        self.root.geometry("800x600")
        self.root.resizable(True, True)

        self.client: Client | None = None
        self.config: Config | None = None
        self.config_path: Path = DEFAULT_CONFIG_PATH

        self.state = ThreadSafeState()
        self.asyncio_manager = AsyncioManager()
        self.asyncio_manager.set_state_callback(self._on_async_state_change)
        self.asyncio_manager.set_error_callback(self._on_async_error)

        self.asyncio_manager.start()

        self.state.register_callback(self._on_state_change)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self._create_config_tab()
        self._create_status_tab()
        self._create_log_tab()
        self._create_about_tab()

        self._create_menu()
        self._create_status_bar()

        add_gui_log_handler(self._add_log_message)

        self._load_config()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load Config", command=self._load_config_dialog)
        file_menu.add_command(label="Save Config", command=self._save_config_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Help", command=self._show_help)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def _create_status_bar(self):
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
        config_frame = ttk.Frame(self.notebook)
        self.notebook.add(config_frame, text="Configuration")

        config_notebook = ttk.Notebook(config_frame)
        config_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        client_frame = ttk.Frame(config_notebook)
        config_notebook.add(client_frame, text="Client")

        server_frame = ttk.Frame(config_notebook)
        config_notebook.add(server_frame, text="Server")

        crypto_frame = ttk.Frame(config_notebook)
        config_notebook.add(crypto_frame, text="Crypto")

        tls_frame = ttk.Frame(config_notebook)
        config_notebook.add(tls_frame, text="TLS")

        ttk.Label(client_frame, text="Local Host:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        self.local_host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(client_frame, textvariable=self.local_host_var, width=30).grid(row=0, column=1, padx=10, pady=5)

        ttk.Label(client_frame, text="Local Port:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        self.local_port_var = tk.StringVar(value="1080")
        ttk.Entry(client_frame, textvariable=self.local_port_var, width=10).grid(row=1, column=1, padx=10, pady=5)

        ttk.Label(server_frame, text="Server Host:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        self.server_host_var = tk.StringVar(value="")
        ttk.Entry(server_frame, textvariable=self.server_host_var, width=30).grid(row=0, column=1, padx=10, pady=5)

        ttk.Label(server_frame, text="Server Port:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        self.server_port_var = tk.StringVar(value="8388")
        ttk.Entry(server_frame, textvariable=self.server_port_var, width=10).grid(row=1, column=1, padx=10, pady=5)

        ttk.Label(crypto_frame, text="Master Key:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        self.master_key_var = tk.StringVar(value="")
        ttk.Entry(crypto_frame, textvariable=self.master_key_var, width=50, show="*").grid(row=0, column=1, padx=10, pady=5)

        ttk.Label(crypto_frame, text="Cipher:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        self.cipher_var = tk.StringVar(value="aes-256-gcm")
        cipher_values = ["aes-256-gcm", "chacha20-poly1305"]
        ttk.Combobox(crypto_frame, textvariable=self.cipher_var, values=cipher_values, width=20).grid(row=1, column=1, padx=10, pady=5)

        ttk.Label(crypto_frame, text="Protocol:").grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
        self.protocol_var = tk.StringVar(value="shadowsocks2022")
        protocol_values = ["shadowsocks2022"]
        ttk.Combobox(crypto_frame, textvariable=self.protocol_var, values=protocol_values, width=20).grid(row=2, column=1, padx=10, pady=5)

        ttk.Label(tls_frame, text="Enabled:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        self.tls_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tls_frame, variable=self.tls_enabled_var).grid(row=0, column=1, padx=10, pady=5, sticky=tk.W)

        ttk.Label(tls_frame, text="WebSocket Enabled:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        self.websocket_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tls_frame, variable=self.websocket_enabled_var).grid(row=1, column=1, padx=10, pady=5, sticky=tk.W)

        ttk.Label(tls_frame, text="WebSocket Path:").grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
        self.websocket_path_var = tk.StringVar(value="/linkman")
        ttk.Entry(tls_frame, textvariable=self.websocket_path_var, width=30).grid(row=2, column=1, padx=10, pady=5)

        ttk.Button(config_frame, text="Save Configuration", command=self._save_config).pack(pady=10)

    def _create_status_tab(self):
        status_frame = ttk.Frame(self.notebook)
        self.notebook.add(status_frame, text="Status")

        status_top = ttk.Frame(status_frame)
        status_top.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(status_top, text="Connection Status:", font=('Helvetica', 12, 'bold')).pack(anchor=tk.W)

        self.status_text = tk.Text(status_top, height=10, width=70)
        self.status_text.pack(fill=tk.BOTH, expand=True, pady=5)
        self.status_text.insert(tk.END, "Not connected\n")
        self.status_text.config(state=tk.DISABLED)

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

        control_frame = ttk.Frame(status_frame)
        control_frame.pack(fill=tk.X, padx=10, pady=10)

        self.connect_button = ttk.Button(control_frame, text="Connect", command=self._connect)
        self.connect_button.pack(side=tk.LEFT, padx=5)

        self.disconnect_button = ttk.Button(control_frame, text="Disconnect", command=self._disconnect, state=tk.DISABLED)
        self.disconnect_button.pack(side=tk.LEFT, padx=5)

        self.refresh_button = ttk.Button(control_frame, text="Refresh", command=self._refresh_status)
        self.refresh_button.pack(side=tk.LEFT, padx=5)

    def _create_log_tab(self):
        log_frame = ttk.Frame(self.notebook)
        self.notebook.add(log_frame, text="Logs")

        self.log_text = tk.Text(log_frame, height=20, width=80)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.log_text.config(state=tk.DISABLED)

        ttk.Button(log_frame, text="Clear Logs", command=self._clear_logs).pack(side=tk.RIGHT, padx=10, pady=5)

    def _create_about_tab(self):
        about_frame = ttk.Frame(self.notebook)
        self.notebook.add(about_frame, text="About")

        about_text = """LinkMan VPN

Version: 1.0.0

A high-performance, secure VPN implementation based on Shadowsocks 2022 protocol.

Features:
- High Performance: Optimized async IO and buffer management
- Secure: AEAD encryption (AES-256-GCM / ChaCha20-Poly1305)
- Flexible: TCP / TLS / WebSocket transport support
- Reliable: Connection pooling and health checking
- Monitorable: Comprehensive metrics collection
- Extensible: Modular architecture"""

        ttk.Label(about_frame, text=about_text, justify=tk.LEFT).pack(padx=20, pady=20)

    def _load_config(self, path: Path | None = None):
        if path is not None:
            self.config_path = path
        else:
            DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        try:
            if self.config_path.exists():
                self.config = Config.load(self.config_path)
                self._update_config_widgets()
                self.status_var.set(f"Loaded config from {self.config_path}")
            else:
                self.config = Config()
                self._update_config_widgets()
                self.status_var.set("Using default config. Please configure and save.")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.config = Config()
            messagebox.showerror("Error", f"Failed to load config: {e}")

    def _load_config_dialog(self):
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="Load Configuration",
            filetypes=[("TOML files", "*.toml"), ("All files", "*")]
        )

        if path:
            self._load_config(Path(path))

    def _save_config(self, path: Path | None = None):
        if self.config is None:
            self.config = Config()

        if path is not None:
            self.config_path = path
        else:
            DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        try:
            self._update_config_from_widgets()
            self.config.save(self.config_path)
            self.status_var.set(f"Saved config to {self.config_path}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            messagebox.showerror("Error", f"Failed to save config: {e}")

    def _save_config_dialog(self):
        from tkinter import filedialog

        path = filedialog.asksaveasfilename(
            title="Save Configuration",
            defaultextension=".toml",
            filetypes=[("TOML files", "*.toml"), ("All files", "*")]
        )

        if path:
            self._save_config(Path(path))

    def _update_config_widgets(self):
        if self.config is None:
            return

        self.local_host_var.set(self.config.client.local_host)
        self.local_port_var.set(str(self.config.client.local_port))
        self.server_host_var.set(self.config.client.server_host)
        self.server_port_var.set(str(self.config.client.server_port))
        self.master_key_var.set(self.config.crypto.key)
        self.cipher_var.set(self.config.crypto.cipher)

        if hasattr(self.config, 'protocol'):
            self.protocol_var.set(self.config.protocol)

        self.tls_enabled_var.set(self.config.tls.enabled)
        self.websocket_enabled_var.set(self.config.tls.websocket_enabled)
        self.websocket_path_var.set(self.config.tls.websocket_path)

    def _update_config_from_widgets(self):
        if self.config is None:
            self.config = Config()

        self.config.client.local_host = self.local_host_var.get()
        try:
            self.config.client.local_port = int(self.local_port_var.get())
        except ValueError:
            pass

        self.config.client.server_host = self.server_host_var.get()
        try:
            self.config.client.server_port = int(self.server_port_var.get())
        except ValueError:
            pass

        self.config.crypto.key = self.master_key_var.get()
        self.config.crypto.cipher = self.cipher_var.get()

        if not hasattr(self.config, 'protocol'):
            self.config.protocol = "shadowsocks2022"
        self.config.protocol = self.protocol_var.get()

        self.config.tls.enabled = self.tls_enabled_var.get()
        self.config.tls.websocket_enabled = self.websocket_enabled_var.get()
        self.config.tls.websocket_path = self.websocket_path_var.get()

    def _connect(self):
        if self.state.is_connected:
            messagebox.showinfo("Info", "Already connected")
            return

        try:
            self._save_config()

            self.client = Client(self.config)

            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.status_var.set("Connecting...")

            self.asyncio_manager.start_client(self.client)
        except Exception as e:
            logger.error(f"Error connecting: {e}")
            messagebox.showerror("Error", f"Failed to connect: {e}")
            self.state.update("is_connected", False)
            self.connect_button.config(state=tk.NORMAL)
            self.disconnect_button.config(state=tk.DISABLED)

    def _disconnect(self):
        if not self.state.is_connected:
            messagebox.showinfo("Info", "Not connected")
            return

        try:
            self.asyncio_manager.stop()

            self.state.update("is_connected", False)
            self.state.reset()
            self.connect_button.config(state=tk.NORMAL)
            self.disconnect_button.config(state=tk.DISABLED)
            self.status_var.set("Disconnected")
            self._update_status()
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
            messagebox.showerror("Error", f"Failed to disconnect: {e}")

    def _refresh_status(self):
        self._update_status()

    def _update_status(self):
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete(1.0, tk.END)

        if self.state.is_connected and self.client:
            self.status_text.insert(tk.END, "Status: Connected\n")
            if self.config:
                self.status_text.insert(tk.END, f"Server: {self.config.client.server_host}:{self.config.client.server_port}\n")
                self.status_text.insert(tk.END, f"Local: {self.config.client.local_host}:{self.config.client.local_port}\n")

            sent = self.state.get("bytes_sent", 0)
            received = self.state.get("bytes_received", 0)
            self.bytes_sent_var.set(f"{sent}")
            self.bytes_received_var.set(f"{received}")
        else:
            self.status_text.insert(tk.END, "Status: Not connected\n")
            self.bytes_sent_var.set("0")
            self.bytes_received_var.set("0")

        self.status_text.config(state=tk.DISABLED)

    def _add_log_message(self, message: str, level: str):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{level}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _clear_logs(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _show_help(self):
        help_text = """LinkMan VPN Help

1. Configuration:
   - Enter server details in the Configuration tab
   - Paste your master key (generated on the server)
   - Save the configuration

2. Connection:
   - Click "Connect" to start the VPN tunnel
   - Click "Disconnect" to stop the VPN tunnel

3. Status:
   - View connection status and traffic statistics
   - Click "Refresh" to update statistics

4. Logs:
   - View real-time application logs

For more information, visit the documentation."""
        messagebox.showinfo("Help", help_text)

    def _show_about(self):
        about_text = """LinkMan VPN

Version: 1.0.0

A high-performance, secure VPN implementation based on Shadowsocks 2022 protocol.
Secure encrypted proxy with traffic obfuscation."""
        messagebox.showinfo("About", about_text)

    def _on_close(self):
        if self.state.is_connected:
            if messagebox.askyesno("Confirm", "Are you sure you want to disconnect and exit?"):
                self._disconnect()

        self.asyncio_manager.stop()
        self.state.unregister_callback(self._on_state_change)

        remove_gui_log_handler(self._add_log_message)

        self.root.destroy()

    def _on_async_state_change(self, key: str, value: Any) -> None:
        self.state.update(key, value)

    def _on_async_error(self, message: str) -> None:
        self.root.after(0, lambda: messagebox.showerror("Connection Error", message))
        self.root.after(0, self._on_connection_lost)

    def _on_state_change(self, key: str, value: Any) -> None:
        if key == "is_connected" and not value:
            self.root.after(0, self._on_connection_lost)
        elif key == "status":
            status_texts = {
                "connecting": "Connecting...",
                "connected": "Connected",
                "disconnecting": "Disconnecting...",
                "disconnected": "Disconnected",
                "error": "Connection Error",
            }
            self.root.after(0, lambda: self.status_var.set(status_texts.get(value, value)))
        self.root.after(0, self._update_status)

    def _on_connection_lost(self) -> None:
        self.connect_button.config(state=tk.NORMAL)
        self.disconnect_button.config(state=tk.DISABLED)
        self._update_status()


def main():
    root = tk.Tk()
    app = LinkManGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
