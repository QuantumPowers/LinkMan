"""
LinkMan VPN Client GUI application.

Provides a simple graphical interface for managing the VPN client.
"""

from __future__ import annotations

import asyncio
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from linkman.shared.utils.config import Config
from linkman.shared.utils.logger import get_logger, setup_logger
from linkman.client.main import Client
from linkman.client.proxy.modes import ProxyMode

logger = get_logger("client.gui")


class LinkManGUI:
    """
    LinkMan VPN Client GUI application.
    """

    def __init__(self, root: tk.Tk):
        """
        Initialize GUI application.

        Args:
            root: Tkinter root window
        """
        self.root = root
        self.root.title("LinkMan VPN Client")
        self.root.geometry("400x300")
        self.root.resizable(False, False)

        # Load configuration
        try:
            self.config = Config.load("linkman.toml")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load configuration: {e}")
            self.root.destroy()
            return

        # Initialize client
        self.client: Optional[Client] = None
        self.is_running = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None

        # Create GUI elements
        self.create_widgets()

        # Set up close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_widgets(self) -> None:
        """
        Create GUI widgets.
        """
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Status label
        self.status_var = tk.StringVar(value="Status: Disconnected")
        status_label = ttk.Label(main_frame, textvariable=self.status_var, font=('Arial', 12, 'bold'))
        status_label.pack(pady=10)

        # Mode selection
        mode_frame = ttk.Frame(main_frame)
        mode_frame.pack(pady=10, fill=tk.X)

        ttk.Label(mode_frame, text="Mode:").pack(side=tk.LEFT, padx=5)
        self.mode_var = tk.StringVar(value="global")
        mode_combo = ttk.Combobox(mode_frame, textvariable=self.mode_var, values=["global", "rules", "direct"], width=10)
        mode_combo.pack(side=tk.LEFT, padx=5)

        # Start/Stop button
        self.start_stop_var = tk.StringVar(value="Start VPN")
        self.start_stop_button = ttk.Button(
            main_frame, 
            textvariable=self.start_stop_var, 
            command=self.toggle_vpn, 
            width=20
        )
        self.start_stop_button.pack(pady=20)

        # Traffic stats
        stats_frame = ttk.LabelFrame(main_frame, text="Traffic Stats")
        stats_frame.pack(pady=10, fill=tk.X)

        self.sent_var = tk.StringVar(value="Sent: 0 B")
        self.received_var = tk.StringVar(value="Received: 0 B")

        ttk.Label(stats_frame, textvariable=self.sent_var).pack(anchor=tk.W, padx=10, pady=5)
        ttk.Label(stats_frame, textvariable=self.received_var).pack(anchor=tk.W, padx=10, pady=5)

        # Status log
        log_frame = ttk.LabelFrame(main_frame, text="Status Log")
        log_frame.pack(pady=10, fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, height=5, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Scrollbar for log
        scrollbar = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

    def toggle_vpn(self) -> None:
        """
        Toggle VPN connection.
        """
        if not self.is_running:
            self.start_vpn()
        else:
            self.stop_vpn()

    def start_vpn(self) -> None:
        """
        Start VPN connection.
        """
        try:
            # Create client
            self.client = Client(self.config)
            
            # Set mode
            mode = self.mode_var.get()
            self.client.set_mode(ProxyMode(mode))

            # Start client in a separate thread
            self.loop = asyncio.new_event_loop()
            self.thread = threading.Thread(target=self._run_client, daemon=True)
            self.thread.start()

            # Update UI
            self.is_running = True
            self.start_stop_var.set("Stop VPN")
            self.status_var.set("Status: Connecting...")
            self.log("Starting VPN client...")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to start VPN: {e}")
            self.log(f"Error: {e}")

    def stop_vpn(self) -> None:
        """
        Stop VPN connection.
        """
        if not self.is_running or not self.loop:
            return

        try:
            # Stop client
            asyncio.run_coroutine_threadsafe(self.client.stop(), self.loop)

            # Update UI
            self.is_running = False
            self.start_stop_var.set("Start VPN")
            self.status_var.set("Status: Disconnected")
            self.log("Stopping VPN client...")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to stop VPN: {e}")
            self.log(f"Error: {e}")

    def _run_client(self) -> None:
        """
        Run client in a separate thread.
        """
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.client.run())
        except Exception as e:
            self.log(f"Client error: {e}")
            # Update UI in main thread
            self.root.after(0, lambda: self.status_var.set("Status: Error"))
            self.root.after(0, lambda: self.start_stop_var.set("Start VPN"))
            self.root.after(0, lambda: setattr(self, "is_running", False))

    def log(self, message: str) -> None:
        """
        Add message to log.

        Args:
            message: Message to add
        """
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def on_close(self) -> None:
        """
        Handle window close event.
        """
        if self.is_running:
            self.stop_vpn()
        self.root.destroy()


def main() -> None:
    """
    Main entry point for GUI application.
    """
    setup_logger(level="INFO")
    root = tk.Tk()
    app = LinkManGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()