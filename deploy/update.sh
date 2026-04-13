#!/bin/bash
#
# LinkMan Server Update Script
# Run this script to update LinkMan to a new version
#

set -e

# Get current user
if [ -n "$SUDO_USER" ]; then
    # Running as root via sudo
    SERVICE_USER="$SUDO_USER"
elif [ "$EUID" -eq 0 ]; then
    # Running as root directly (not recommended)
    echo "Error: Please run this script with sudo from your regular user account"
    echo "Example: sudo bash deploy/update.sh"
    exit 1
else
    # Running as regular user
    SERVICE_USER="$(whoami)"
fi

INSTALL_DIR="/home/$SERVICE_USER/linkman"
BACKUP_DIR="/home/$SERVICE_USER/linkman-backup-$(date +%Y%m%d_%H%M%S)"

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
echo "  LinkMan Server Update Script"
echo "=========================================="
echo "Service user: $SERVICE_USER"
echo "Installation directory: $INSTALL_DIR"

if [ "$EUID" -ne 0 ]; then
    print_error "Please run with sudo"
    echo "Example: sudo bash deploy/update.sh"
    exit 1
fi

print_step "Stopping service"
if systemctl stop linkman || true; then
    print_success "Service stopped successfully"
else
    print_error "Failed to stop service"
    # Continue even if service stop fails
fi

print_step "Backing up configuration"
if mkdir -p $BACKUP_DIR && cp $INSTALL_DIR/linkman.toml $BACKUP_DIR/ && cp -r $INSTALL_DIR/data $BACKUP_DIR/ 2>/dev/null || true; then
    print_success "Configuration backed up successfully"
else
    print_error "Failed to backup configuration"
    exit 1
fi

print_step "Updating code"
if cd $INSTALL_DIR && sudo -u $SERVICE_USER git pull; then
    print_success "Code updated successfully"
else
    print_error "Failed to update code"
    exit 1
fi

source $INSTALL_DIR/venv/bin/activate

if pip install --upgrade pip && pip install -r requirements.txt && pip install -e .; then
    print_success "Dependencies updated successfully"
else
    print_error "Failed to update dependencies"
    exit 1
fi

print_step "Restoring configuration"
if cp $BACKUP_DIR/linkman.toml $INSTALL_DIR/ && [ -d "$BACKUP_DIR/data" ] && cp -r $BACKUP_DIR/data $INSTALL_DIR/; then
    print_success "Configuration restored successfully"
else
    print_error "Failed to restore configuration"
    exit 1
fi

print_step "Starting service"
if systemctl start linkman; then
    print_success "Service started successfully"
else
    print_error "Failed to start service"
    exit 1
fi

# Summary
echo ""
echo "=========================================="
echo "  Update Summary"
echo "=========================================="
echo "Total steps: $TOTAL_STEPS"
echo "Success: $SUCCESS_COUNT"
echo "Errors: $ERROR_COUNT"
echo "Completion: $((SUCCESS_COUNT * 100 / TOTAL_STEPS))%"
echo ""

if [ $ERROR_COUNT -eq 0 ]; then
    echo "🎉 Update Complete!"
    echo ""
    echo "Backup saved to: $BACKUP_DIR"
    echo ""
    echo "Check status with:"
    echo "  sudo systemctl status linkman"
    echo ""
else
    echo "❌ Update failed with $ERROR_COUNT error(s)"
    echo "Please check the error messages above and try again."
    exit 1
fi
