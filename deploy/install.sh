#!/bin/bash
#
# LinkMan Server Installation Script
# Run this script on your server to install LinkMan
#

set -e

INSTALL_DIR="/opt/linkman"
SERVICE_USER="linkman"
PYTHON_VERSION="3.11"

echo "=========================================="
echo "  LinkMan Server Installation Script"
echo "=========================================="

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root"
    exit 1
fi

echo "[1/7] Installing dependencies..."
apt-get update
apt-get install -y python3 python3-pip python3-venv nginx certbot

echo "[2/7] Creating service user..."
if ! id -u $SERVICE_USER &>/dev/null; then
    useradd -r -s /bin/false $SERVICE_USER
fi

echo "[3/7] Creating directories..."
mkdir -p $INSTALL_DIR
mkdir -p $INSTALL_DIR/data
mkdir -p $INSTALL_DIR/logs

echo "[4/7] Setting up Python virtual environment..."
python3 -m venv $INSTALL_DIR/venv
source $INSTALL_DIR/venv/bin/activate

echo "[5/7] Installing LinkMan..."
if [ -f "requirements.txt" ]; then
    pip install --upgrade pip
    pip install -r requirements.txt
fi

if [ -d "src" ]; then
    pip install -e .
fi

echo "[6/7] Creating configuration..."
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
file = "/opt/linkman/logs/linkman.log"
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

KEY=$(python3 -c "from linkman.shared.crypto.keys import KeyManager; print(KeyManager().master_key_base64)")
sed -i "s/^key = \"\"/key = \"$KEY\"/" $INSTALL_DIR/linkman.toml

echo "[7/7] Installing systemd service..."
cat > /etc/systemd/system/linkman.service << EOF
[Unit]
Description=LinkMan VPN Server
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/linkman-server -c $INSTALL_DIR/linkman.toml
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
echo "  systemctl start linkman"
echo ""
echo "To check status:"
echo "  systemctl status linkman"
echo ""
echo "To view logs:"
echo "  journalctl -u linkman -f"
echo ""
