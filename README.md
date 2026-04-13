# LinkMan VPN

一个安全、高效的 VPN 代理工具，基于 Shadowsocks 2022 协议，支持流量混淆和加密通信。

## 特性

- ✅ **安全加密**: 使用 AES-256-GCM 和 ChaCha20-Poly1305 等现代加密算法
- ✅ **高性能**: 优化的数据转发和加密解密处理
- ✅ **UDP 支持**: 完善的 UDP 协议支持
- ✅ **多平台**: 支持 Linux、macOS 和 Windows
- ✅ **流量管理**: 内置流量统计和限制功能
- ✅ **设备管理**: 支持多设备连接和设备限制
- ✅ **监控系统**: 实时监控服务器状态和性能
- ✅ **TLS 伪装**: 支持 TLS 加密和流量混淆

## 快速开始

### 服务器部署

1. **安装依赖**

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip

# CentOS/RHEL
sudo dnf install -y python3.11 python3.11-venv python3-pip
```

2. **安装 LinkMan**

```bash
# 克隆代码
git clone https://github.com/yourusername/linkman.git
cd linkman

# 创建虚拟环境
python3.11 -m venv venv
source venv/bin/activate

# 安装依赖
pip install --upgrade pip
pip install -e .
```

3. **生成密钥**

```bash
# 生成新密钥
python -m linkman.server.main --generate-key
```

4. **创建配置文件**

```bash
cp linkman.toml.example linkman.toml
# 编辑配置文件，设置密钥和其他选项
```

5. **启动服务器**

```bash
# 启动服务器
python -m linkman.server.main -c linkman.toml

# 或使用系统服务 (详见 deploy.md)
```

### 客户端使用

1. **安装客户端**

```bash
# 安装客户端
pip install -e .[client]
```

2. **创建客户端配置**

```bash
cat > linkman-client.toml << EOF
[client]
local_host = "127.0.0.1"
local_port = 1080
server_host = "your-server-ip"
server_port = 8388

[crypto]
cipher = "aes-256-gcm"
key = "your-server-key"
EOF
```

3. **启动客户端**

```bash
# 启动客户端
python -m linkman.client.main -c linkman-client.toml --mode rules

# 或使用 GUI 客户端 (PyQt6)
```

4. **测试连接**

```bash
# 测试代理
curl -x socks5://127.0.0.1:1080 http://httpbin.org/ip
```

## 配置选项

### 服务器配置

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `server.host` | 服务器监听地址 | `0.0.0.0` |
| `server.port` | 服务器监听端口 | `8388` |
| `server.management_port` | 管理 API 端口 | `8389` |
| `server.max_connections` | 最大并发连接数 | `1024` |
| `server.connection_timeout` | 连接超时时间 (秒) | `300` |
| `server.buffer_size` | 缓冲区大小 | `65536` |

### 客户端配置

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `client.local_host` | 本地代理地址 | `127.0.0.1` |
| `client.local_port` | 本地代理端口 | `1080` |
| `client.server_host` | 服务器地址 | - |
| `client.server_port` | 服务器端口 | `8388` |
| `client.connection_timeout` | 连接超时时间 (秒) | `30` |
| `client.buffer_size` | 缓冲区大小 | `65536` |

### 加密配置

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `crypto.cipher` | 加密算法 | `aes-256-gcm` |
| `crypto.key` | 加密密钥 | - |
| `crypto.identity` | 客户端标识 | - |

### 流量配置

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `traffic.enabled` | 启用流量统计 | `true` |
| `traffic.limit_mb` | 流量限制 (MB) | `0` (无限制) |
| `traffic.warning_threshold_mb` | 流量警告阈值 (MB) | `1000` |
| `traffic.reset_day` | 流量重置日 | `1` (每月 1 日) |

### 设备配置

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `device.max_devices` | 最大设备数 | `5` |
| `device.session_timeout` | 会话超时时间 (秒) | `3600` |
| `device.allowed_devices` | 允许的设备列表 | `[]` |

### 日志配置

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `log.level` | 日志级别 | `INFO` |
| `log.file` | 日志文件路径 | `logs/linkman.log` |
| `log.max_size_mb` | 日志文件最大大小 (MB) | `10` |
| `log.backup_count` | 日志备份数量 | `5` |
| `log.format` | 日志格式 | `{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}` |

### TLS 配置

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `tls.enabled` | 启用 TLS | `false` |
| `tls.cert_file` | 证书文件路径 | - |
| `tls.key_file` | 密钥文件路径 | - |
| `tls.domain` | 域名 | - |
| `tls.websocket_path` | WebSocket 路径 | `/linkman` |

## 代理模式

LinkMan 支持三种代理模式：

1. **global**: 全局代理，所有流量都通过 VPN
2. **rules**: 规则模式，根据规则决定是否使用 VPN
3. **direct**: 直连模式，不使用 VPN

```bash
# 启动客户端时指定模式
python -m linkman.client.main --mode rules
```

## API 接口

LinkMan 提供了 RESTful API 接口，用于管理服务器：

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/status` | GET | 获取服务器状态 |
| `/api/devices` | GET | 获取设备列表 |
| `/api/traffic` | GET | 获取流量统计 |
| `/api/sessions` | GET | 获取会话列表 |
| `/api/config` | GET | 获取配置信息 |
| `/api/config` | PUT | 更新配置 |

## 常见问题

### Q: 服务器启动失败？

- 检查端口是否被占用
- 检查配置文件是否正确
- 查看日志文件了解详细错误

### Q: 客户端连接不上？

- 检查服务器防火墙是否开放端口
- 检查密钥是否正确
- 检查服务器 IP 和端口是否正确
- 测试网络连通性：`telnet server-ip 8388`

### Q: 速度慢？

- 尝试更换加密算法（ChaCha20-Poly1305 可能更快）
- 检查服务器带宽和网络延迟
- 调整缓冲区大小

### Q: 如何更新？

```bash
# 拉取最新代码
git pull

# 重新安装
source venv/bin/activate
pip install -e .

# 重启服务
systemctl restart linkman
```

## 安全建议

1. **定期更换密钥**
2. **启用 TLS 伪装**
3. **限制管理 API 访问**
4. **设置合理的流量限制**
5. **定期检查日志**
6. **使用强密码**

## 性能优化

1. **使用 uvloop**：提高 asyncio 性能
2. **调整缓冲区大小**：根据网络情况调整
3. **选择合适的加密算法**：根据 CPU 性能选择
4. **启用压缩**：在带宽有限的情况下

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License
