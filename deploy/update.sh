#!/bin/bash
#
# LinkMan Server Update Script
# Run this script to update LinkMan to a new version
#

set -e

INSTALL_DIR="/opt/linkman"
BACKUP_DIR="/opt/linkman-backup-$(date +%Y%m%d_%H%M%S)"

echo "=========================================="
echo "  LinkMan Server Update Script"
echo "=========================================="

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root"
    exit 1
fi

echo "[1/5] Stopping service..."
systemctl stop linkman || true

echo "[2/5] Backing up configuration..."
mkdir -p $BACKUP_DIR
cp $INSTALL_DIR/linkman.toml $BACKUP_DIR/
cp -r $INSTALL_DIR/data $BACKUP_DIR/ 2>/dev/null || true

echo "[3/5] Updating code..."
source $INSTALL_DIR/venv/bin/activate

if [ -f "requirements.txt" ]; then
    pip install --upgrade pip
    pip install -r requirements.txt
fi

if [ -d "src" ]; then
    pip install -e .
fi

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
echo "  systemctl status linkman"
echo ""
