#!/bin/bash
#
# LinkMan VPN Local Deployment Script
# This script prepares the local client environment
#

set -e

# Get current user
SERVICE_USER="$(whoami)"

DEPLOY_DIR="$HOME/linkman"
CONFIG_FILE="$DEPLOY_DIR/linkman.toml"
ENV_FILE="$DEPLOY_DIR/.env"

# Progress tracking
TOTAL_STEPS=5
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
echo "  LinkMan VPN Local Deployment Script"
echo "=========================================="
echo "User: $SERVICE_USER"
echo "Deployment directory: $DEPLOY_DIR"
echo ""
echo "This script will:"
echo "1. Check system environment"
echo "2. Install dependencies"
echo "3. Create configuration files"
echo "4. Configure client settings"
echo "5. Test client connection"
echo ""

print_step "Checking system environment"
# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed"
    echo "Please install Python 3 before continuing"
    exit 1
else
    print_success "Python 3 is installed"
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

# Create virtual environment
cd "$DEPLOY_DIR"
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
if pip install --upgrade pip && pip install -r requirements.txt && pip install .; then
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

# Encryption key (obtain from server)
ENCRYPTION_KEY=""

# Server settings
SERVER_HOST="your-server-ip"
SERVER_PORT=8388
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
key = ""  # Obtain from server
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

print_step "Configuring client settings"
echo ""
echo "=========================================="
echo "  CLIENT CONFIGURATION"
echo "=========================================="
echo "Please enter the following information (obtain from server):"
echo ""

# Get server host
read -p "Server IP or domain: " SERVER_HOST
if [ -n "$SERVER_HOST" ]; then
    # Update configuration file
    sed -i "s/^server_host = \"[^"]*\"/server_host = \"$SERVER_HOST\"/" "$CONFIG_FILE"
    # Update .env file
    sed -i "s/^SERVER_HOST=\"[\"]*\"/SERVER_HOST=\"$SERVER_HOST\"/" "$ENV_FILE"
    print_success "Server host updated to $SERVER_HOST"
else
    print_error "Server host is required"
    exit 1
fi

# Get encryption key
read -p "Encryption key: " ENCRYPTION_KEY
if [ -n "$ENCRYPTION_KEY" ]; then
    # Update configuration file
    sed -i "s/^key = \"[^"]*\"/key = \"$ENCRYPTION_KEY\"/" "$CONFIG_FILE"
    # Update .env file
    sed -i "s/^ENCRYPTION_KEY=\"[\"]*\"/ENCRYPTION_KEY=\"$ENCRYPTION_KEY\"/" "$ENV_FILE"
    print_success "Encryption key updated"
else
    print_error "Encryption key is required"
    exit 1
fi

# Get server port
read -p "Server port (default: 8388): " SERVER_PORT
if [ -n "$SERVER_PORT" ]; then
    # Update configuration file
    sed -i "s/^server_port = [0-9]*/server_port = $SERVER_PORT/" "$CONFIG_FILE"
    # Update .env file
    sed -i "s/^SERVER_PORT=[0-9]*/SERVER_PORT=$SERVER_PORT/" "$ENV_FILE"
    print_success "Server port updated to $SERVER_PORT"
else
    print_success "Using default server port: 8388"
fi

print_step "Testing client connection"
echo ""
echo "=========================================="
echo "  CONNECTION TEST"
echo "=========================================="
echo "Testing client configuration..."
echo ""

# Test if configuration is valid
if python3 -c "from linkman.shared.utils.config import Config; config = Config.load('$CONFIG_FILE'); errors = config.validate(); print('Configuration validation:', 'OK' if not errors else 'ERROR: ' + ', '.join(errors))"; then
    print_success "Client configuration is valid"
else
    print_error "Client configuration is invalid"
    exit 1
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
    echo "🎉 Local Deployment Complete!"
    echo ""
    echo "IMPORTANT NOTES:"
    echo "1. Client configuration is ready"
    echo "2. Configuration files created:"
    echo "   - $CONFIG_FILE"
    echo "   - $ENV_FILE (contains sensitive information)"
    echo ""
    echo "3. To start the client:"
    echo "   source $DEPLOY_DIR/venv/bin/activate"
    echo "   python -m linkman.client.main -c $DEPLOY_DIR/linkman.toml"
    echo ""
    echo "4. To check client logs:"
    echo "   tail -f $DEPLOY_DIR/logs/linkman.log"
    echo ""
    echo "5. Make sure the server is running before starting the client"
else
    echo "❌ Deployment failed with $ERROR_COUNT error(s)"
    echo "Please check the error messages above and try again."
    exit 1
fi