#!/bin/bash
#
# SSL Certificate Setup Script
# Uses Let's Encrypt to obtain SSL certificate
#

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <domain>"
    echo "Example: $0 example.com"
    exit 1
fi

DOMAIN=$1
CERT_DIR="/etc/letsencrypt/live/$DOMAIN"

echo "=========================================="
echo "  SSL Certificate Setup"
echo "=========================================="

echo "[1/3] Obtaining certificate..."
certbot certonly --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN

echo "[2/3] Setting up auto-renewal..."
cat > /etc/cron.d/certbot << EOF
0 0 * * * root certbot renew --quiet --post-hook "systemctl reload nginx"
EOF

echo "[3/3] Updating LinkMan configuration..."
CONFIG_FILE="/opt/linkman/linkman.toml"
if [ -f "$CONFIG_FILE" ]; then
    sed -i "s|^enabled = false|enabled = true|" $CONFIG_FILE
    sed -i "s|^cert_file = .*|cert_file = \"$CERT_DIR/fullchain.pem\"|" $CONFIG_FILE
    sed -i "s|^key_file = .*|key_file = \"$CERT_DIR/privkey.pem\"|" $CONFIG_FILE
    sed -i "s|^domain = .*|domain = \"$DOMAIN\"|" $CONFIG_FILE
    
    echo ""
    echo "Configuration updated. Restart LinkMan:"
    echo "  systemctl restart linkman"
fi

echo ""
echo "=========================================="
echo "  Certificate Setup Complete!"
echo "=========================================="
echo ""
echo "Certificate files:"
echo "  Cert: $CERT_DIR/fullchain.pem"
echo "  Key:  $CERT_DIR/privkey.pem"
echo ""
echo "Auto-renewal is configured via cron."
echo ""
