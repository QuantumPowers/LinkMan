"""
System proxy manager for LinkMan VPN client.

Handles:
- Automatic system proxy configuration
- Restoring original proxy settings on exit
- Cross-platform support (macOS, Windows, Linux)
"""

from __future__ import annotations

import platform
import subprocess
import sys
from typing import Dict, Optional

from linkman.shared.utils.logger import get_logger

logger = get_logger("client.proxy_manager")


class ProxyManager:
    """
    Manages system proxy settings.
    
    Automatically configures system proxy when VPN starts
    and restores original settings when VPN stops.
    """

    def __init__(self, host: str, port: int):
        """
        Initialize proxy manager.

        Args:
            host: Proxy server host
            port: Proxy server port
        """
        self._host = host
        self._port = port
        self._original_settings: Optional[Dict[str, str]] = None
        self._platform = platform.system()

    def set_proxy(self) -> bool:
        """
        Set system proxy settings.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Setting system proxy to {self._host}:{self._port}")
            
            # Save original settings
            self._original_settings = self._get_current_settings()
            logger.debug(f"Original proxy settings: {self._original_settings}")

            # Set proxy based on platform
            if self._platform == "Darwin":  # macOS
                return self._set_mac_proxy()
            elif self._platform == "Windows":
                return self._set_windows_proxy()
            elif self._platform == "Linux":
                return self._set_linux_proxy()
            else:
                logger.warning(f"Unsupported platform: {self._platform}")
                return False

        except Exception as e:
            logger.error(f"Failed to set proxy: {e}")
            return False

    def restore_proxy(self) -> bool:
        """
        Restore original system proxy settings.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self._original_settings:
                logger.debug("No original proxy settings to restore")
                return True

            logger.info("Restoring original proxy settings")

            # Restore proxy based on platform
            if self._platform == "Darwin":  # macOS
                return self._restore_mac_proxy()
            elif self._platform == "Windows":
                return self._restore_windows_proxy()
            elif self._platform == "Linux":
                return self._restore_linux_proxy()
            else:
                logger.warning(f"Unsupported platform: {self._platform}")
                return False

        except Exception as e:
            logger.error(f"Failed to restore proxy: {e}")
            return False

    def _get_current_settings(self) -> Dict[str, str]:
        """
        Get current proxy settings.

        Returns:
            Dict[str, str]: Current proxy settings
        """
        settings = {}
        
        try:
            if self._platform == "Darwin":  # macOS
                # Get current proxy settings using networksetup
                result = subprocess.run(
                    ["networksetup", "-getwebproxy", "Wi-Fi"],
                    capture_output=True,
                    text=True
                )
                settings["web_proxy"] = result.stdout
                
                result = subprocess.run(
                    ["networksetup", "-getsecurewebproxy", "Wi-Fi"],
                    capture_output=True,
                    text=True
                )
                settings["secure_web_proxy"] = result.stdout
                
                result = subprocess.run(
                    ["networksetup", "-getsocksfirewallproxy", "Wi-Fi"],
                    capture_output=True,
                    text=True
                )
                settings["socks_proxy"] = result.stdout

        except Exception as e:
            logger.debug(f"Failed to get current proxy settings: {e}")

        return settings

    def _set_mac_proxy(self) -> bool:
        """
        Set proxy settings on macOS.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Set SOCKS proxy
            subprocess.run(
                ["networksetup", "-setsocksfirewallproxystate", "Wi-Fi", "on"],
                check=True
            )
            subprocess.run(
                ["networksetup", "-setsocksfirewallproxy", "Wi-Fi", self._host, str(self._port)],
                check=True
            )
            
            # Set web proxy
            subprocess.run(
                ["networksetup", "-setwebproxystate", "Wi-Fi", "on"],
                check=True
            )
            subprocess.run(
                ["networksetup", "-setwebproxy", "Wi-Fi", self._host, str(self._port)],
                check=True
            )
            
            # Set secure web proxy
            subprocess.run(
                ["networksetup", "-setsecurewebproxystate", "Wi-Fi", "on"],
                check=True
            )
            subprocess.run(
                ["networksetup", "-setsecurewebproxy", "Wi-Fi", self._host, str(self._port)],
                check=True
            )
            
            logger.info("macOS proxy settings updated successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to set macOS proxy: {e}")
            return False

    def _restore_mac_proxy(self) -> bool:
        """
        Restore proxy settings on macOS.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self._original_settings:
                return True

            # Restore SOCKS proxy
            if "socks_proxy" in self._original_settings:
                output = self._original_settings["socks_proxy"]
                if "Enabled: No" in output:
                    subprocess.run(
                        ["networksetup", "-setsocksfirewallproxystate", "Wi-Fi", "off"],
                        check=True
                    )
                else:
                    # Extract host and port from output
                    host = None
                    port = None
                    for line in output.splitlines():
                        if "Server:" in line:
                            host = line.split(":")[1].strip()
                        elif "Port:" in line:
                            port = line.split(":")[1].strip()
                    if host and port:
                        subprocess.run(
                            ["networksetup", "-setsocksfirewallproxy", "Wi-Fi", host, port],
                            check=True
                        )
                        subprocess.run(
                            ["networksetup", "-setsocksfirewallproxystate", "Wi-Fi", "on"],
                            check=True
                        )

            # Restore web proxy
            if "web_proxy" in self._original_settings:
                output = self._original_settings["web_proxy"]
                if "Enabled: No" in output:
                    subprocess.run(
                        ["networksetup", "-setwebproxystate", "Wi-Fi", "off"],
                        check=True
                    )
                else:
                    # Extract host and port from output
                    host = None
                    port = None
                    for line in output.splitlines():
                        if "Server:" in line:
                            host = line.split(":")[1].strip()
                        elif "Port:" in line:
                            port = line.split(":")[1].strip()
                    if host and port:
                        subprocess.run(
                            ["networksetup", "-setwebproxy", "Wi-Fi", host, port],
                            check=True
                        )
                        subprocess.run(
                            ["networksetup", "-setwebproxystate", "Wi-Fi", "on"],
                            check=True
                        )

            # Restore secure web proxy
            if "secure_web_proxy" in self._original_settings:
                output = self._original_settings["secure_web_proxy"]
                if "Enabled: No" in output:
                    subprocess.run(
                        ["networksetup", "-setsecurewebproxystate", "Wi-Fi", "off"],
                        check=True
                    )
                else:
                    # Extract host and port from output
                    host = None
                    port = None
                    for line in output.splitlines():
                        if "Server:" in line:
                            host = line.split(":")[1].strip()
                        elif "Port:" in line:
                            port = line.split(":")[1].strip()
                    if host and port:
                        subprocess.run(
                            ["networksetup", "-setsecurewebproxy", "Wi-Fi", host, port],
                            check=True
                        )
                        subprocess.run(
                            ["networksetup", "-setsecurewebproxystate", "Wi-Fi", "on"],
                            check=True
                        )

            logger.info("macOS proxy settings restored successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to restore macOS proxy: {e}")
            return False

    def _set_windows_proxy(self) -> bool:
        """
        Set proxy settings on Windows.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # TODO: Implement Windows proxy settings
            logger.warning("Windows proxy settings not yet implemented")
            return False

        except Exception as e:
            logger.error(f"Failed to set Windows proxy: {e}")
            return False

    def _restore_windows_proxy(self) -> bool:
        """
        Restore proxy settings on Windows.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # TODO: Implement Windows proxy settings
            logger.warning("Windows proxy settings not yet implemented")
            return False

        except Exception as e:
            logger.error(f"Failed to restore Windows proxy: {e}")
            return False

    def _set_linux_proxy(self) -> bool:
        """
        Set proxy settings on Linux.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # TODO: Implement Linux proxy settings
            logger.warning("Linux proxy settings not yet implemented")
            return False

        except Exception as e:
            logger.error(f"Failed to set Linux proxy: {e}")
            return False

    def _restore_linux_proxy(self) -> bool:
        """
        Restore proxy settings on Linux.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # TODO: Implement Linux proxy settings
            logger.warning("Linux proxy settings not yet implemented")
            return False

        except Exception as e:
            logger.error(f"Failed to restore Linux proxy: {e}")
            return False