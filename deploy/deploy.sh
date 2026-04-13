#!/bin/bash
#
# LinkMan VPN Deployment Script
# This script automates the deployment process, including key generation
#

set -e

# Get current user
if [ -n "$SUDO_USER" ]; then
    # Running as root via sudo
    SERVICE_USER="$SUDO_USER"
elif [ "$EUID" -eq 0 ]; then
    # Running as root directly (not recommended)
    echo "Error: Please run this script with sudo from your regular user account"
    echo "Example: sudo bash deploy/deploy.sh"
    exit 1
else
    # Running as regular user
    SERVICE_USER="$(whoami)"
fi

DEPLOY_DIR="/home/$SERVICE_USER/linkman"

# Progress tracking
TOTAL_STEPS=8
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
echo "  LinkMan VPN Deployment Script"
echo "=========================================="
echo "Service user: $SERVICE_USER"
echo "Deployment directory: $DEPLOY_DIR"

echo ""
echo "This script will:"
echo "1. Stop any running LinkMan service"
echo "2. Update code from Git"
echo "3. Create/Update virtual environment"
echo "4. Install dependencies"
echo "5. Generate encryption key"
echo "6. Update configuration file"
echo "7. Restart LinkMan service"
echo "8. Show deployment status"
echo ""

if [ "$EUID" -ne 0 ]; then
    print_error "Please run with sudo"
    echo "Example: sudo bash deploy/deploy.sh"
    exit 1
fi

print_step "Stopping LinkMan service"
if systemctl is-active --quiet linkman; then
    if systemctl stop linkman; then
        print_success "LinkMan service stopped"
    else
        print_error "Failed to stop LinkMan service"
    fi
else
    print_success "LinkMan service is not running"
fi

print_step "Updating code from Git"
if [ -d "$DEPLOY_DIR" ]; then
    cd "$DEPLOY_DIR"
    if git pull; then
        print_success "Code updated successfully"
    else
        print_error "Failed to update code"
        # Continue with deployment even if Git pull fails
    fi
else
    print_error "Deployment directory not found"
    echo "Please run install.sh first to create the deployment directory"
    exit 1
fi

print_step "Updating virtual environment"
cd "$DEPLOY_DIR"
if [ -d "venv" ]; then
    source venv/bin/activate
    print_success "Virtual environment activated"
else
    if python3 -m venv venv; then
        source venv/bin/activate
        print_success "Virtual environment created"
    else
        print_error "Failed to create virtual environment"
        exit 1
    fi
fi

print_step "Installing dependencies"
if pip install --upgrade pip && pip install -r requirements.txt && pip install .; then
    print_success "Dependencies installed successfully"
else
    print_error "Failed to install dependencies"
    exit 1
fi

print_step "Generating encryption key"
KEY=$(python3 -c "from linkman.shared.crypto.keys import KeyManager; key = KeyManager.generate_master_key(); print(KeyManager(key).master_key_base64)")
if [ -z "$KEY" ]; then
    print_error "Failed to generate encryption key"
    exit 1
fi
print_success "Encryption key generated"

print_step "Updating configuration file"
CONFIG_FILE="$DEPLOY_DIR/linkman.toml"
if [ -f "$CONFIG_FILE" ]; then
    # Update key in configuration file
    sed -i "s/^key = \"[^"]*\"/key = \"$KEY\"/" "$CONFIG_FILE"
    
    # Update TLS configuration if not already set
    sed -i "s/^enabled = false/enabled = true/" "$CONFIG_FILE"
    
    # Add placeholder for domain if not set
    if grep -q "domain = \"\"" "$CONFIG_FILE"; then
        sed -i "s/^domain = \"\"/domain = \"YOUR_DOMAIN_OR_IP\"/" "$CONFIG_FILE"
    fi
    
    print_success "Configuration file updated"
else
    print_error "Configuration file not found"
    echo "Please run install.sh first to create the configuration file"
    exit 1
fi

print_step "Restarting LinkMan service"
if systemctl daemon-reload && systemctl start linkman; then
    print_success "LinkMan service started"
else
    print_error "Failed to start LinkMan service"
fi

print_step "Checking deployment status"
sleep 2  # Give service time to start
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
    echo "1. Encryption key has been automatically generated and updated"
    echo "2. TLS is enabled by default"
    echo "3. Please update the following in $CONFIG_FILE:"
    echo "   - domain = \"YOUR_DOMAIN_OR_IP\"  # Replace with your actual domain or IP"
    echo "   - port = 8388  # Change if needed"
    echo "   - management_port = 8389  # Change if needed"
    echo ""
    echo "4. If using TLS with a domain, run certbot to get a real certificate:"
    echo "   sudo bash $DEPLOY_DIR/deploy/certbot.sh"
    echo ""
    echo "5. To check service status:"
    echo "   sudo systemctl status linkman"
    echo ""
    echo "6. To view logs:"
    echo "   sudo journalctl -u linkman -f"
else
    echo "❌ Deployment failed with $ERROR_COUNT error(s)"
    echo "Please check the error messages above and try again."
    exit 1
fi