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

echo "=========================================="
echo "  LinkMan Server Update Script"
echo "=========================================="
echo "Service user: $SERVICE_USER"
echo "Installation directory: $INSTALL_DIR"

if [ "$EUID" -ne 0 ]; then
    echo "Please run with sudo"
    echo "Example: sudo bash deploy/update.sh"
    exit 1
fi

echo "[1/5] Stopping service..."
systemctl stop linkman || true

echo "[2/5] Backing up configuration..."
mkdir -p $BACKUP_DIR
cp $INSTALL_DIR/linkman.toml $BACKUP_DIR/
cp -r $INSTALL_DIR/data $BACKUP_DIR/ 2>/dev/null || true

echo "[3/5] Updating code..."
cd $INSTALL_DIR
sudo -u $SERVICE_USER git pull

source $INSTALL_DIR/venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
pip install -e .

echo "[4/5] Restoring configuration..."
cp $BACKUP_DIR/linkman.toml $INSTALL_DIR/
if [ -d "$BACKUP_DIR/data" ]; then
    cp -r $BACKUP_DIR/data $INSTALL_DIR/
fi

echo "[5/5] Starting service..."
systemctl start linkman

echo ""
echo "=========================================="
echo "  Update Complete!"
echo "=========================================="
echo ""
echo "Backup saved to: $BACKUP_DIR"
echo ""
echo "Check status with:"
echo "  sudo systemctl status linkman"
echo ""
