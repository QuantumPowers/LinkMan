# LinkMan 部署指南

## 目录

1. [服务器要求](#服务器要求)
2. [快速部署](#快速部署)
3. [手动部署](#手动部署)
4. [TLS证书配置](#tls证书配置)
5. [客户端配置](#客户端配置)
6. [常见问题](#常见问题)

---

## 服务器要求

- **操作系统**: Ubuntu 20.04+ / Debian 11+
- **Python**: 3.11+
- **内存**: 最低 512MB
- **网络**: 开放 8388 和 8389 端口

---

## 快速部署

### 步骤 1: 上传代码到服务器

```bash
# 在本地执行，将代码上传到服务器
scp -r /Users/reeseche/Documents/trae_projects/LinkMan root@YOUR_SERVER_IP:/opt/
```

### 步骤 2: 运行安装脚本

```bash
# SSH 登录服务器
ssh root@YOUR_SERVER_IP

# 进入项目目录
cd /opt/LinkMan

# 运行安装脚本
chmod +x deploy/install.sh
./deploy/install.sh
```

### 步骤 3: 配置密钥

```bash
# 生成新密钥
KEY=$(python3 -c "from linkman.shared.crypto.keys import KeyManager; print(KeyManager().master_key_base64)")
echo "你的密钥: $KEY"

# 更新配置文件
sed -i "s/^key = \"\"/key = \"$KEY\"/" /opt/linkman/linkman.toml
```

### 步骤 4: 启动服务

```bash
systemctl start linkman
systemctl status linkman
```

---

## 手动部署

### 步骤 1: 安装依赖

```bash
# 更新系统
apt update && apt upgrade -y

# 安装 Python 3.11
apt install -y python3.11 python3.11-venv python3-pip

# 安装 Nginx (用于 TLS 伪装)
apt install -y nginx certbot
```

### 步骤 2: 创建用户

```bash
useradd -r -s /bin/false linkman
```

### 步骤 3: 部署代码

```bash
# 创建目录
mkdir -p /opt/linkman
mkdir -p /opt/linkman/data
mkdir -p /opt/linkman/logs

# 复制代码
cp -r src /opt/linkman/
cp pyproject.toml /opt/linkman/
cp requirements.txt /opt/linkman/

# 创建虚拟环境
cd /opt/linkman
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

### 步骤 4: 创建配置文件

```bash
cat > /opt/linkman/linkman.toml << 'EOF'
[server]
host = "0.0.0.0"
port = 8388
management_port = 8389
max_connections = 1024
connection_timeout = 300
buffer_size = 65536

[crypto]
cipher = "aes-256-gcm"
key = "YOUR_KEY_HERE"  # 替换为生成的密钥

[traffic]
enabled = true
limit_mb = 0
warning_threshold_mb = 1000
reset_day = 1

[device]
max_devices = 5
session_timeout = 3600

[log]
level = "INFO"
file = "/opt/linkman/logs/linkman.log"
max_size_mb = 10
backup_count = 5

[tls]
enabled = false
EOF
```

### 步骤 5: 生成密钥

```bash
# 生成密钥
source /opt/linkman/venv/bin/activate
KEY=$(python3 -c "from linkman.shared.crypto.keys import KeyManager; print(KeyManager().master_key_base64)")
echo "生成的密钥: $KEY"

# 更新配置
sed -i "s/YOUR_KEY_HERE/$KEY/" /opt/linkman/linkman.toml
```

### 步骤 6: 安装系统服务

```bash
cat > /etc/systemd/system/linkman.service << 'EOF'
[Unit]
Description=LinkMan VPN Server
After=network.target

[Service]
Type=simple
User=linkman
Group=linkman
WorkingDirectory=/opt/linkman
ExecStart=/opt/linkman/venv/bin/linkman-server -c /opt/linkman/linkman.toml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 设置权限
chown -R linkman:linkman /opt/linkman

# 启动服务
systemctl daemon-reload
systemctl enable linkman
systemctl start linkman
```

### 步骤 7: 验证服务

```bash
# 检查状态
systemctl status linkman

# 查看日志
journalctl -u linkman -f

# 测试 API
curl http://localhost:8389/
```

---

## TLS证书配置

### 使用 Let's Encrypt (推荐)

```bash
# 申请证书 (替换 YOUR_DOMAIN)
certbot certonly --nginx -d YOUR_DOMAIN

# 配置 Nginx
cp /opt/LinkMan/deploy/nginx.conf /etc/nginx/sites-available/linkman
ln -s /etc/nginx/sites-available/linkman /etc/nginx/sites-enabled/

# 编辑配置，替换 YOUR_DOMAIN
sed -i "s/YOUR_DOMAIN/你的域名/g" /etc/nginx/sites-available/linkman

# 测试并重载
nginx -t
systemctl reload nginx

# 更新 LinkMan 配置
sed -i "s/enabled = false/enabled = true/" /opt/linkman/linkman.toml
sed -i "s|^cert_file = .*|cert_file = \"/etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem\"|" /opt/linkman/linkman.toml
sed -i "s|^key_file = .*|key_file = \"/etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem\"|" /opt/linkman/linkman.toml
sed -i "s|^domain = .*|domain = \"YOUR_DOMAIN\"|" /opt/linkman/linkman.toml

# 重启服务
systemctl restart linkman
```

---

## 客户端配置

### macOS 客户端

```bash
# 创建客户端配置
cat > ~/linkman-client.toml << EOF
[client]
local_host = "127.0.0.1"
local_port = 1080
server_host = "YOUR_SERVER_IP"
server_port = 8388

[crypto]
cipher = "aes-256-gcm"
key = "YOUR_KEY"  # 服务端生成的密钥
EOF

# 启动客户端
python -m linkman.client.main -c ~/linkman-client.toml --mode rules
```

### 测试代理

```bash
# 测试连接
curl -x socks5://127.0.0.1:1080 http://httpbin.org/ip

# 应该返回服务器的 IP 地址
```

### 配置系统代理

**方式一：终端代理**
```bash
export http_proxy=socks5://127.0.0.1:1080
export https_proxy=socks5://127.0.0.1:1080
```

**方式二：系统设置**
1. 系统偏好设置 → 网络 → 高级 → 代理
2. SOCKS代理: 127.0.0.1:1080

---

## 防火墙配置

### Ubuntu/Debian (ufw)

```bash
ufw allow 8388/tcp
ufw allow 8389/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

### CentOS/RHEL (firewalld)

```bash
firewall-cmd --permanent --add-port=8388/tcp
firewall-cmd --permanent --add-port=8389/tcp
firewall-cmd --permanent --add-port=80/tcp
firewall-cmd --permanent --add-port=443/tcp
firewall-cmd --reload
```

---

## 常用命令

```bash
# 启动服务
systemctl start linkman

# 停止服务
systemctl stop linkman

# 重启服务
systemctl restart linkman

# 查看状态
systemctl status linkman

# 查看日志
journalctl -u linkman -f

# 查看实时连接
curl http://localhost:8389/api/status

# 查看设备列表
curl http://localhost:8389/api/devices

# 查看流量统计
curl http://localhost:8389/api/traffic
```

---

## 常见问题

### Q: 服务无法启动？

```bash
# 检查日志
journalctl -u linkman -n 50

# 检查配置
cat /opt/linkman/linkman.toml

# 检查端口占用
netstat -tlnp | grep 8388
```

### Q: 客户端连接不上？

1. 检查服务器防火墙是否开放端口
2. 检查密钥是否正确
3. 检查服务器 IP 是否正确

```bash
# 测试端口连通性
telnet YOUR_SERVER_IP 8388
```

### Q: 如何更新？

```bash
cd /opt/LinkMan
git pull  # 或重新上传代码
./deploy/update.sh
```

### Q: 如何查看当前密钥？

```bash
grep "^key" /opt/linkman/linkman.toml
```

---

## 安全建议

1. **定期更换密钥**
2. **启用 TLS 伪装**
3. **限制管理 API 访问** (修改 Nginx 配置)
4. **定期检查日志**
5. **设置流量限制**

---

## 联系支持

如有问题，请查看项目文档或提交 Issue。
