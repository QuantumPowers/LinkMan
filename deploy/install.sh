#!/bin/bash
#
# LinkMan Server Installation Script
# Run this script on your server to install LinkMan
#

set -e

# Get current user
if [ -n "$SUDO_USER" ]; then
    # Running as root via sudo
    SERVICE_USER="$SUDO_USER"
elif [ "$EUID" -eq 0 ]; then
    # Running as root directly (not recommended)
    echo "Error: Please run this script with sudo from your regular user account"
    echo "Example: sudo bash deploy/install.sh"
    exit 1
else
    # Running as regular user
    SERVICE_USER="$(whoami)"
fi

INSTALL_DIR="/home/$SERVICE_USER/linkman"

echo "=========================================="
echo "  LinkMan Server Installation Script"
echo "=========================================="
echo "Service user: $SERVICE_USER"
echo "Installation directory: $INSTALL_DIR"

if [ "$EUID" -ne 0 ]; then
    echo "Please run with sudo"
    echo "Example: sudo bash deploy/install.sh"
    exit 1
fi

echo "[1/6] Installing dependencies..."
apt-get update
apt-get install -y python3 python3-pip python3-venv nginx certbot

echo "[2/6] Creating directories..."
mkdir -p $INSTALL_DIR
mkdir -p $INSTALL_DIR/data
mkdir -p $INSTALL_DIR/logs

echo "[3/6] Setting up Python virtual environment..."
python3 -m venv $INSTALL_DIR/venv
source $INSTALL_DIR/venv/bin/activate

echo "[4/6] Installing LinkMan..."
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .

echo "[5/6] Creating configuration..."
if [ ! -f "$INSTALL_DIR/linkman.toml" ]; then
    cat > $INSTALL_DIR/linkman.toml << 'EOF'
[server]
host = "0.0.0.0"
port = 8388
management_port = 8389
max_connections = 1024
connection_timeout = 300
buffer_size = 65536

[crypto]
cipher = "aes-256-gcm"
key = ""  # Will be generated

[traffic]
enabled = true
limit_mb = 0
warning_threshold_mb = 1000
reset_day = 1

[device]
max_devices = 5
session_timeout = 3600
allowed_devices = []

[log]
level = "INFO"
file = "/home/linkman/linkman/logs/linkman.log"
max_size_mb = 10
backup_count = 5

[tls]
enabled = false
cert_file = ""
key_file = ""
domain = ""
websocket_path = "/linkman"
EOF
fi

# Update log path in configuration
sed -i "s|/home/linkman/linkman/logs/linkman.log|/home/$SERVICE_USER/linkman/logs/linkman.log|" $INSTALL_DIR/linkman.toml

KEY=$(python3 -c "from linkman.shared.crypto.keys import KeyManager; print(KeyManager().master_key_base64)")
sed -i "s/^key = \"\"/key = \"$KEY\"/" $INSTALL_DIR/linkman.toml

echo "[6/6] Installing systemd service..."
cat > /etc/systemd/system/linkman.service << EOF
[Unit]
Description=LinkMan VPN Server
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python -m linkman.server.main -c $INSTALL_DIR/linkman.toml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

chown -R $SERVICE_USER:$SERVICE_USER $INSTALL_DIR

systemctl daemon-reload
systemctl enable linkman

echo ""
echo "=========================================="
echo "  Installation Complete!"
echo "=========================================="
echo ""
echo "Configuration file: $INSTALL_DIR/linkman.toml"
echo "Encryption key has been generated."
echo ""
echo "To start the server:"
echo "  sudo systemctl start linkman"
echo ""
echo "To check status:"
echo "  sudo systemctl status linkman"
echo ""
echo "To view logs:"
echo "  sudo journalctl -u linkman -f"
echo ""
