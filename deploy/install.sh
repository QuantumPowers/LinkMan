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

# Progress tracking
TOTAL_STEPS=6
CURRENT_STEP=0
ERROR_COUNT=0
SUCCESS_COUNT=0

# Function to print step header
print_step() {
    CURRENT_STEP=$((CURRENT_STEP + 1))
    echo ""
    echo "=========================================="
    echo "  Step $CURRENT_STEP/$TOTAL_STEPS: $1"
    echo "=========================================="
}

# Function to print success
print_success() {
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    echo "✅ $1"
}

# Function to print error
print_error() {
    ERROR_COUNT=$((ERROR_COUNT + 1))
    echo "❌ $1"
}

echo "=========================================="
echo "  LinkMan Server Installation Script"
echo "=========================================="
echo "Service user: $SERVICE_USER"
echo "Installation directory: $INSTALL_DIR"

if [ "$EUID" -ne 0 ]; then
    print_error "Please run with sudo"
    echo "Example: sudo bash deploy/install.sh"
    exit 1
fi

print_step "Installing dependencies"
if apt-get update && apt-get install -y python3 python3-pip python3-venv nginx certbot; then
    print_success "Dependencies installed successfully"
else
    print_error "Failed to install dependencies"
    exit 1
fi

print_step "Creating directories"
if mkdir -p $INSTALL_DIR && mkdir -p $INSTALL_DIR/data && mkdir -p $INSTALL_DIR/logs; then
    print_success "Directories created successfully"
else
    print_error "Failed to create directories"
    exit 1
fi

print_step "Setting up Python virtual environment"
if python3 -m venv $INSTALL_DIR/venv; then
    source $INSTALL_DIR/venv/bin/activate
    print_success "Virtual environment created successfully"
else
    print_error "Failed to create virtual environment"
    exit 1
fi

print_step "Installing LinkMan"
if pip install --upgrade pip && pip install -r requirements.txt && pip install -e .; then
    print_success "LinkMan installed successfully"
else
    print_error "Failed to install LinkMan"
    exit 1
fi

print_step "Creating configuration"
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

# Generate secure encryption key
KEY=$(python3 -c "from linkman.shared.crypto.keys import KeyManager; key = KeyManager.generate_master_key(); print(KeyManager(key).master_key_base64)")
sed -i "s/^key = \"\"/key = \"$KEY\"/" $INSTALL_DIR/linkman.toml

# Update TLS configuration with placeholder for user input
sed -i "s/^enabled = false/enabled = true/" $INSTALL_DIR/linkman.toml
sed -i "s/^domain = \"\"/domain = \"YOUR_DOMAIN_OR_IP\"/" $INSTALL_DIR/linkman.toml

# Add installation summary with important notes
echo ""
echo "=========================================="
echo "  IMPORTANT CONFIGURATION NOTES"
echo "=========================================="
echo "1. Encryption key has been automatically generated"
echo "2. TLS is enabled by default"
echo "3. Please update the following in $INSTALL_DIR/linkman.toml:"
echo "   - domain = \"YOUR_DOMAIN_OR_IP\"  # Replace with your actual domain or IP"
echo "   - port = 8388  # Change if needed"
echo "   - management_port = 8389  # Change if needed"
echo ""
echo "4. If using TLS with a domain, run certbot to get a real certificate:"
echo "   sudo bash $INSTALL_DIR/deploy/certbot.sh"
echo ""
echo "5. Start the server:"
echo "   sudo systemctl start linkman"


print_success "Configuration created successfully"

print_step "Installing systemd service"
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

if chown -R $SERVICE_USER:$SERVICE_USER $INSTALL_DIR && systemctl daemon-reload && systemctl enable linkman; then
    print_success "Systemd service installed successfully"
else
    print_error "Failed to install systemd service"
    exit 1
fi

# Summary
echo ""
echo "=========================================="
echo "  Installation Summary"
echo "=========================================="
echo "Total steps: $TOTAL_STEPS"
echo "Success: $SUCCESS_COUNT"
echo "Errors: $ERROR_COUNT"
echo "Completion: $((SUCCESS_COUNT * 100 / TOTAL_STEPS))%"
echo ""

if [ $ERROR_COUNT -eq 0 ]; then
    echo "🎉 Installation Complete!"
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
else
    echo "❌ Installation failed with $ERROR_COUNT error(s)"
    echo "Please check the error messages above and try again."
    exit 1
fi
