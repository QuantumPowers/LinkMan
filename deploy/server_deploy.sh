#!/bin/bash
#
# LinkMan VPN Server Deployment Script
# This script automates the server deployment process
#

set -e

# Get current user
if [ -n "$SUDO_USER" ]; then
    # Running as root via sudo
    SERVICE_USER="$SUDO_USER"
elif [ "$EUID" -eq 0 ]; then
    # Running as root directly (not recommended)
    echo "Error: Please run this script with sudo from your regular user account"
    echo "Example: sudo bash deploy/server_deploy.sh"
    exit 1
else
    # Running as regular user
    SERVICE_USER="$(whoami)"
fi

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

DEPLOY_DIR="/home/$SERVICE_USER/linkman"
CONFIG_FILE="$DEPLOY_DIR/linkman.toml"
ENV_FILE="$DEPLOY_DIR/.env"

# Progress tracking
TOTAL_STEPS=7
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
echo "  LinkMan VPN Server Deployment Script"
echo "=========================================="
echo "Service user: $SERVICE_USER"
echo "Deployment directory: $DEPLOY_DIR"
echo ""
echo "This script will:"
echo "1. Check system environment"
echo "2. Install dependencies"
echo "3. Create configuration files"
echo "4. Generate encryption key"
echo "5. Configure TLS settings"
echo "6. Install systemd service"
echo "7. Start LinkMan service"
echo ""

if [ "$EUID" -ne 0 ]; then
    print_error "Please run with sudo"
    echo "Example: sudo bash deploy/server_deploy.sh"
    exit 1
fi

print_step "Checking system environment"
# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed"
    echo "Installing Python 3..."
    if apt-get update && apt-get install -y python3 python3-pip python3-venv; then
        print_success "Python 3 installed successfully"
    else
        print_error "Failed to install Python 3"
        exit 1
    fi
else
    print_success "Python 3 is installed"
fi

# Check if Git is installed
if ! command -v git &> /dev/null; then
    print_error "Git is not installed"
    echo "Installing Git..."
    if apt-get update && apt-get install -y git; then
        print_success "Git installed successfully"
    else
        print_error "Failed to install Git"
        exit 1
    fi
else
    print_success "Git is installed"
fi

print_step "Installing dependencies"
# Create deployment directory if it doesn't exist
if [ ! -d "$DEPLOY_DIR" ]; then
    if mkdir -p "$DEPLOY_DIR" && chown -R "$SERVICE_USER:$SERVICE_USER" "$DEPLOY_DIR"; then
        print_success "Deployment directory created"
    else
        print_error "Failed to create deployment directory"
        exit 1
    fi
fi

# Copy project files to deployment directory
if [ "$PROJECT_DIR" != "$DEPLOY_DIR" ]; then
    print_success "Copying project files to deployment directory"
    cp -r "$PROJECT_DIR"/* "$DEPLOY_DIR/" 2>/dev/null || true
    cp -r "$PROJECT_DIR"/.* "$DEPLOY_DIR/" 2>/dev/null || true
fi

# Change to deployment directory
cd "$DEPLOY_DIR"

# Create virtual environment
if [ ! -d "venv" ]; then
    if python3 -m venv venv; then
        print_success "Virtual environment created"
    else
        print_error "Failed to create virtual environment"
        exit 1
    fi
else
    print_success "Virtual environment exists"
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
if pip install --upgrade pip && pip install -r "$DEPLOY_DIR/requirements.txt" && pip install "$DEPLOY_DIR"; then
    print_success "Dependencies installed successfully"
else
    print_error "Failed to install dependencies"
    exit 1
fi

print_step "Creating configuration files"
# Create .env file for sensitive information
if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" << 'EOF'
# LinkMan Environment Variables
# This file contains sensitive information
# Do not commit this file to version control

# Encryption key will be generated automatically
ENCRYPTION_KEY=""

# TLS settings
TLS_DOMAIN="your-domain.com"
TLS_CERT_FILE=""
TLS_KEY_FILE=""
EOF
    chmod 600 "$ENV_FILE"
    chown "$SERVICE_USER:$SERVICE_USER" "$ENV_FILE"
    print_success ".env file created"
else
    print_success ".env file exists"
fi

# Create configuration file
if [ ! -f "$CONFIG_FILE" ]; then
    cat > "$CONFIG_FILE" << 'EOF'
[server]
host = "0.0.0.0"
port = 8388
management_port = 8389
max_connections = 512
connection_timeout = 300
buffer_size = 32768

[client]
local_host = "127.0.0.1"
local_port = 1080
server_host = "your-server-ip"
server_port = 8388
connection_timeout = 30
buffer_size = 32768

[crypto]
cipher = "chacha20-poly1305"
key = ""  # Will be generated automatically
identity = ""

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
file = "logs/linkman.log"
max_size_mb = 10
backup_count = 5
format = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"

[tls]
enabled = true
cert_file = ""
key_file = ""
domain = "your-domain.com"
websocket_path = "/api/ws"
EOF
    chmod 600 "$CONFIG_FILE"
    chown "$SERVICE_USER:$SERVICE_USER" "$CONFIG_FILE"
    print_success "Configuration file created"
else
    print_success "Configuration file exists"
fi

print_step "Generating encryption key"
# Generate encryption key
KEY=$(python3 -c "from linkman.shared.crypto.keys import KeyManager; key = KeyManager.generate_master_key(); print(KeyManager(key).master_key_base64)")
if [ -z "$KEY" ]; then
    print_error "Failed to generate encryption key"
    exit 1
fi

# Update configuration file
sed -i "s/^key = \"[^"]*\"/key = \"$KEY\"/" "$CONFIG_FILE"

# Update .env file
sed -i "s/^ENCRYPTION_KEY=\"[\"]*\"/ENCRYPTION_KEY=\"$KEY\"/" "$ENV_FILE"

print_success "Encryption key generated and updated"

print_step "Configuring TLS settings"
# Ask for domain
read -p "Enter your domain (press Enter to use existing): " DOMAIN
if [ -n "$DOMAIN" ]; then
    # Update configuration file
    sed -i "s/^domain = \"[^"]*\"/domain = \"$DOMAIN\"/" "$CONFIG_FILE"
    # Update .env file
    sed -i "s/^TLS_DOMAIN=\"[\"]*\"/TLS_DOMAIN=\"$DOMAIN\"/" "$ENV_FILE"
    print_success "Domain updated to $DOMAIN"
else
    print_success "Using existing domain"
fi

print_step "Installing systemd service"
# Create systemd service file
cat > /etc/systemd/system/linkman.service << EOF
[Unit]
Description=LinkMan VPN Server
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$DEPLOY_DIR
ExecStart=$DEPLOY_DIR/venv/bin/python -m linkman.server.main -c $DEPLOY_DIR/linkman.toml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload

# Enable service
systemctl enable linkman

print_success "Systemd service installed and enabled"

print_step "Starting LinkMan service"
# Start service
if systemctl start linkman; then
    print_success "LinkMan service started"
else
    print_error "Failed to start LinkMan service"
fi

# Give service time to start
sleep 2

# Check service status
if systemctl is-active --quiet linkman; then
    print_success "LinkMan service is running"
    
    # Get service status
    STATUS=$(systemctl status linkman --no-pager | grep -E "Active:|Main PID|")
    echo "Service status:"
    echo "$STATUS"
    
    # Get server ports
    PORTS=$(netstat -tuln | grep -E "8388|8389")
    echo ""
    echo "Server ports:"
    echo "$PORTS"
else
    print_error "LinkMan service is not running"
    echo "Check logs with: sudo journalctl -u linkman -f"
fi

# Summary
echo ""
echo "=========================================="
echo "  Deployment Summary"
echo "=========================================="
echo "Total steps: $TOTAL_STEPS"
echo "Success: $SUCCESS_COUNT"
echo "Errors: $ERROR_COUNT"
echo "Completion: $((SUCCESS_COUNT * 100 / TOTAL_STEPS))%"
echo ""

if [ $ERROR_COUNT -eq 0 ]; then
    echo "🎉 Deployment Complete!"
    echo ""
    echo "IMPORTANT NOTES:"
    echo "1. Encryption key has been automatically generated"
    echo "2. TLS is enabled by default"
    echo "3. Configuration files created:"
    echo "   - $CONFIG_FILE"
    echo "   - $ENV_FILE (contains sensitive information)"
    echo ""
    echo "4. Service commands:"
    echo "   - Start service: sudo systemctl start linkman"
    echo "   - Stop service: sudo systemctl stop linkman"
    echo "   - Restart service: sudo systemctl restart linkman"
    echo "   - Check status: sudo systemctl status linkman"
    echo "   - View logs: sudo journalctl -u linkman -f"
    echo ""
    echo "5. Client configuration:"
    echo "   - Server address: $(hostname -I | awk '{print $1}')"
    echo "   - Port: 8388"
    echo "   - Encryption key: $KEY"
    echo "   - Encryption method: chacha20-poly1305"
    echo "   - TLS: enabled"
else
    echo "❌ Deployment failed with $ERROR_COUNT error(s)"
    echo "Please check the error messages above and try again."
    exit 1
fi