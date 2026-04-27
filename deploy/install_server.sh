#!/usr/bin/env bash
# ===================================================================
# LinkMan VPN Server - One-click deployment via Git/GitHub
# ===================================================================
# Usage on a fresh Linux server (Ubuntu/Debian 22.04+):
#
#   # First time (fresh install):
#   curl -fsSL https://raw.githubusercontent.com/YOUR_USER/linkman/main/deploy/install_server.sh -o install.sh
#   sudo bash install.sh --repo https://github.com/YOUR_USER/linkman.git
#
#   # Or if you already cloned:
#   git clone https://github.com/YOUR_USER/linkman.git /opt/linkman
#   sudo bash /opt/linkman/deploy/install_server.sh
#
#   # Update to latest version:
#   sudo bash /opt/linkman/deploy/install_server.sh --update
#
# Options:
#   --repo <url>   Git repository URL (first-time only)
#   --update       Pull latest code and reinstall dependencies
#   --branch <n>   Git branch (default: main)
#   --key <k>      Pre-set encryption key (optional, auto-generated otherwise)
# ===================================================================

set -euo pipefail

APP_DIR="/opt/linkman"
VENV_DIR="${APP_DIR}/venv"
USER_NAME="linkman"
CONFIG_FILE="${APP_DIR}/linkman.toml"
SERVER_CONFIG_TEMPLATE="${APP_DIR}/linkman.server.toml"

GIT_REPO=""
GIT_BRANCH="main"
PRESET_KEY=""
DO_UPDATE=false

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "\n${GREEN}============================================${NC}"; echo -e "${GREEN}  $*${NC}"; echo -e "${GREEN}============================================${NC}"; }

# ---------- Parse args ----------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo)   GIT_REPO="$2"; shift 2 ;;
        --branch) GIT_BRANCH="$2"; shift 2 ;;
        --key)    PRESET_KEY="$2"; shift 2 ;;
        --update) DO_UPDATE=true; shift ;;
        *) log_error "Unknown option: $1"; exit 1 ;;
    esac
done

# ---------- Check root ----------
if [ "$(id -u)" -ne 0 ]; then
    log_error "This script must be run as root. Use: sudo bash $0"
    exit 1
fi

# ---------- Install git if missing ----------
if ! command -v git &> /dev/null; then
    log_info "Installing git..."
    apt-get update -qq && apt-get install -y -qq git
fi

# ---------- Clone / update ----------
if [ "$DO_UPDATE" = true ]; then
    log_step "Updating from Git"
    if [ ! -d "${APP_DIR}/.git" ]; then
        log_error "Not a git repository. Use --repo for first-time install."
        exit 1
    fi
    cd "${APP_DIR}"
    sudo -u "${USER_NAME}" git fetch origin
    sudo -u "${USER_NAME}" git reset --hard "origin/${GIT_BRANCH}"
    log_info "Code updated from ${GIT_BRANCH}."
elif [ ! -d "${APP_DIR}/src" ]; then
    if [ -z "${GIT_REPO}" ]; then
        log_error "No code found at ${APP_DIR} and no --repo provided."
        echo ""
        echo "  First-time install:"
        echo "    sudo bash $0 --repo https://github.com/YOUR_USER/linkman.git"
        echo ""
        echo "  Or clone manually first:"
        echo "    git clone https://github.com/YOUR_USER/linkman.git ${APP_DIR}"
        echo "    sudo bash ${APP_DIR}/deploy/install_server.sh"
        exit 1
    fi
    log_step "Cloning from Git"
    rm -rf "${APP_DIR}"
    git clone --branch "${GIT_BRANCH}" "${GIT_REPO}" "${APP_DIR}"
    log_info "Repository cloned to ${APP_DIR}"
else
    log_info "Code already exists at ${APP_DIR}, skipping clone."
    log_info "Use --update to pull latest changes."
fi

log_step "LinkMan VPN Server Deployment"

# ---------- Step 1: System dependencies ----------
log_info "[1/7] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    build-essential \
    libssl-dev \
    libffi-dev \
    > /dev/null 2>&1
log_info "System dependencies installed."

# ---------- Step 2: Create system user ----------
log_info "[2/7] Creating system user '${USER_NAME}'..."
if ! id -u "${USER_NAME}" > /dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "${USER_NAME}"
    log_info "User '${USER_NAME}' created."
else
    log_info "User '${USER_NAME}' already exists."
fi

# ---------- Step 3: Setup directories ----------
log_info "[3/7] Setting up directories..."
mkdir -p "${APP_DIR}/logs" "${APP_DIR}/data" "${APP_DIR}/metrics" "${APP_DIR}/config"
log_info "Directories created."

# ---------- Step 4: Python virtual environment ----------
log_info "[4/7] Creating Python virtual environment..."
if [ "$DO_UPDATE" = true ] && [ -d "${VENV_DIR}" ]; then
    rm -rf "${VENV_DIR}"
    log_info "Removed old virtual environment."
fi
if [ ! -d "${VENV_DIR}" ]; then
    python3.11 -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/pip" install --upgrade pip -q
"${VENV_DIR}/bin/pip" install -e "${APP_DIR}" -q
log_info "Virtual environment ready at ${VENV_DIR}"

# ---------- Step 5: Configuration ----------
log_info "[5/7] Setting up configuration..."
if [ ! -f "${CONFIG_FILE}" ]; then
    if [ -f "${SERVER_CONFIG_TEMPLATE}" ]; then
        cp "${SERVER_CONFIG_TEMPLATE}" "${CONFIG_FILE}"
    elif [ -f "${APP_DIR}/linkman.toml.example" ]; then
        cp "${APP_DIR}/linkman.toml.example" "${CONFIG_FILE}"
    fi
fi

if [ -n "${PRESET_KEY}" ]; then
    log_info "Using provided encryption key."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' 's/^key = ".*"/key = "'"${PRESET_KEY}"'"/' "${CONFIG_FILE}"
    else
        sed -i 's/^key = ".*"/key = "'"${PRESET_KEY}"'"/' "${CONFIG_FILE}"
    fi
else
    CURRENT_KEY=$(grep -E '^key\s*=' "${CONFIG_FILE}" 2>/dev/null | sed 's/.*=\s*"\(.*\)".*/\1/' || true)
    if [ -z "${CURRENT_KEY}" ] || [ "${CURRENT_KEY}" = "" ]; then
        log_info "Generating encryption key..."
        MASTER_KEY=$("${VENV_DIR}/bin/linkman-server" --generate-key 2>/dev/null | grep "Generated key:" | awk '{print $NF}')
        if [ -n "${MASTER_KEY}" ]; then
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' 's/^key = ""/key = "'"${MASTER_KEY}"'"/' "${CONFIG_FILE}"
            else
                sed -i 's/^key = ""/key = "'"${MASTER_KEY}"'"/' "${CONFIG_FILE}"
            fi
            log_info "Encryption key generated and saved."
            echo ""
            log_warn "⚠️  IMPORTANT: Save this key for client configuration:"
            echo ""
            echo -e "    ${GREEN}${MASTER_KEY}${NC}"
            echo ""
        fi
    else
        log_info "Encryption key already configured."
    fi
fi

chown -R "${USER_NAME}:${USER_NAME}" "${APP_DIR}"

# ---------- Step 6: systemd service ----------
log_info "[6/7] Installing systemd service..."
SERVICE_FILE="/etc/systemd/system/linkman.service"

if [ -f "${APP_DIR}/deploy/systemd/linkman.service" ]; then
    cp "${APP_DIR}/deploy/systemd/linkman.service" "${SERVICE_FILE}"
else
    cat > "${SERVICE_FILE}" << 'SYSTEMD_EOF'
[Unit]
Description=LinkMan VPN Server
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=linkman
Group=linkman
WorkingDirectory=/opt/linkman
ExecStart=/opt/linkman/venv/bin/linkman-server -c /opt/linkman/linkman.toml
Restart=on-failure
RestartSec=5
TimeoutStopSec=30

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/linkman/data /opt/linkman/logs /opt/linkman/metrics
ReadOnlyPaths=/etc/ssl/certs

LimitNOFILE=65535
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
SYSTEMD_EOF
fi

systemctl daemon-reload
systemctl enable linkman
log_info "systemd service installed and enabled."

# ---------- Step 7: Nginx (optional) ----------
log_info "[7/7] Checking nginx integration..."
if command -v nginx &> /dev/null; then
    if [ -f "${APP_DIR}/deploy/nginx.conf" ]; then
        NGINX_CONF="/etc/nginx/sites-available/linkman"
        cp "${APP_DIR}/deploy/nginx.conf" "${NGINX_CONF}"

        if [ ! -L "/etc/nginx/sites-enabled/linkman" ]; then
            ln -sf "${NGINX_CONF}" /etc/nginx/sites-enabled/linkman
        fi

        nginx -t && systemctl reload nginx && log_info "Nginx configured and reloaded." || log_warn "Nginx config test failed, check the configuration."
    fi
else
    log_info "Nginx not installed. Skipping nginx setup."
    log_info "Install nginx for TLS obfuscation: sudo apt install nginx certbot python3-certbot-nginx"
fi

# ---------- Summary ----------
echo ""
log_step "Deployment Complete!"
echo ""
echo "  Source code:   ${APP_DIR}  (git repo)"
echo "  Config file:   ${CONFIG_FILE}"
echo "  Logs:          ${APP_DIR}/logs"
echo "  Data (SQLite): ${APP_DIR}/data"
echo ""
echo "  Start server:  sudo systemctl start linkman"
echo "  Stop server:   sudo systemctl stop linkman"
echo "  Status:        sudo systemctl status linkman"
echo "  View logs:     sudo journalctl -u linkman -f"
echo ""
echo "  Update code:   sudo bash ${APP_DIR}/deploy/install_server.sh --update"
echo ""
