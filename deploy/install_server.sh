#!/usr/bin/env bash
# ===================================================================
# LinkMan VPN Server Deployment
# ===================================================================
# Usage (run from the project root):
#   sudo bash deploy/install_server.sh
# ===================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

APP_DIR="/opt/linkman"
VENV_DIR="${APP_DIR}/venv"
USER_NAME="linkman"
CONFIG_FILE="${APP_DIR}/linkman.toml"

if [ "$(id -u)" -ne 0 ]; then
    echo "[ERROR] Must run as root.  sudo bash $0"
    exit 1
fi

log()  { echo "[INFO]  $*"; }
warn() { echo "[WARN]  $*"; }
step() { echo ""; echo "====  $*  ===="; echo ""; }

# ---------- Step 1: System dependencies ----------
step "[1/7] System dependencies"
apt-get update -qq
if ! apt-cache show python3.11 &> /dev/null; then
    apt-get install -y -qq software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -qq
fi
apt-get install -y -qq python3.11 python3.11-venv python3.11-dev python3-pip build-essential libssl-dev libffi-dev
log "Done."

# ---------- Step 2: Copy project ----------
step "[2/7] Copy project to ${APP_DIR}"
rsync -a --delete --exclude='.git' --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' "${PROJECT_DIR}/" "${APP_DIR}/"
log "Done."

# ---------- Step 3: System user ----------
step "[3/7] System user"
if ! id -u "${USER_NAME}" &> /dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "${USER_NAME}"
fi
mkdir -p "${APP_DIR}/logs" "${APP_DIR}/data" "${APP_DIR}/metrics"
log "Done."

# ---------- Step 4: Virtual env ----------
step "[4/7] Python virtual env"
if [ -d "${VENV_DIR}" ]; then rm -rf "${VENV_DIR}"; fi
python3.11 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip -q
"${VENV_DIR}/bin/pip" install -e "${APP_DIR}" -q
log "Done."

# ---------- Step 5: Config ----------
step "[5/7] Configuration"
if [ ! -f "${CONFIG_FILE}" ]; then
    if [ -f "${APP_DIR}/linkman.toml.example" ]; then
        cp "${APP_DIR}/linkman.toml.example" "${CONFIG_FILE}"
    fi
fi
if grep -qE '^key\s*=\s*""' "${CONFIG_FILE}" 2>/dev/null; then
    log "Generating encryption key..."
    MASTER_KEY=$("${VENV_DIR}/bin/linkman-server" --generate-key 2>/dev/null | tail -1)
    if [ -n "${MASTER_KEY}" ]; then
        sed -i 's/^key = ""/key = "'"${MASTER_KEY}"'"/' "${CONFIG_FILE}"
        echo ""
        warn "Save this key — you'll need it for the client:"
        echo "    ${MASTER_KEY}"
        echo ""
    fi
fi
log "Done."

# ---------- Step 6: systemd ----------
step "[6/7] systemd service"
cp "${APP_DIR}/deploy/systemd/linkman.service" /etc/systemd/system/linkman.service
systemctl daemon-reload
systemctl enable linkman
log "Done."

# ---------- Step 7: Nginx (optional) ----------
step "[7/7] Nginx"
if command -v nginx &> /dev/null; then
    NGINX_SITE="/etc/nginx/sites-available/linkman"
    CERT_FILE="/etc/ssl/certs/linkman-selfsigned.crt"
    KEY_FILE="/etc/ssl/private/linkman-selfsigned.key"

    if [ ! -f "${CERT_FILE}" ] || [ ! -f "${KEY_FILE}" ]; then
        log "Generating self-signed certificate..."
        mkdir -p /etc/ssl/private /etc/ssl/certs
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout "${KEY_FILE}" \
            -out "${CERT_FILE}" \
            -subj "/CN=$(hostname)" 2>/dev/null
    fi

    cp "${APP_DIR}/deploy/nginx.conf" "${NGINX_SITE}"
    ln -sf "${NGINX_SITE}" /etc/nginx/sites-enabled/linkman 2>/dev/null || true
    if nginx -t 2>/dev/null; then
        systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null
        log "Nginx configured and running."
    else
        warn "nginx -t failed — removing linkman site to keep nginx healthy."
        rm -f /etc/nginx/sites-enabled/linkman
        log "Removed linkman nginx config. Fix the issue and re-run the script."
    fi
else
    log "Nginx not installed. Skipped."
fi

# ---------- Permissions ----------
chown -R "${USER_NAME}:${USER_NAME}" "${APP_DIR}"

# ---------- Done ----------
echo ""
echo "============================================"
echo "  Deployment Complete"
echo "============================================"
echo ""
echo "  Config:  ${CONFIG_FILE}"
echo "  Logs:    journalctl -u linkman -f"
echo ""
echo "  Start:   sudo systemctl start linkman"
echo "  Status:  sudo systemctl status linkman"
echo ""
