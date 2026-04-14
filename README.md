# LinkMan VPN

LinkMan 是一个基于 Shadowsocks 2022 协议的 VPN 客户端/服务器工具，提供安全、高效的网络代理服务。

## 功能特性

- ✅ 支持 Shadowsocks 2022 协议
- ✅ 支持 AEAD 加密 (AES-256-GCM, ChaCha20-Poly1305)
- ✅ 支持 TLS 加密
- ✅ 支持 WebSocket 流量伪装
- ✅ 支持 UDP 协议
- ✅ 自动系统代理配置
- ✅ 图形界面支持
- ✅ 规则模式（选择性代理）
- ✅ 全球模式（全部代理）
- ✅ 直连模式（不使用代理）
- ✅ 流量统计
- ✅ 错误处理和重试机制

## 安装

### 服务器端

1. **克隆代码**
   ```bash
   git clone https://github.com/QuantumPowers/LinkMan.git
   cd LinkMan
   ```

2. **运行部署脚本**
   ```bash
   sudo bash deploy/server_deploy.sh
   ```

3. **配置服务器**
   部署脚本会自动生成配置文件，您可以根据需要修改 `/home/ubuntu/linkman/linkman.toml`。

### 客户端

1. **克隆代码**
   ```bash
   git clone https://github.com/QuantumPowers/LinkMan.git
   cd LinkMan
   ```

2. **创建虚拟环境**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **安装依赖**
   ```bash
   pip install -e .
   ```

4. **配置客户端**
   复制配置文件示例并修改：
   ```bash
   cp linkman.toml.example linkman.toml
   # 编辑 linkman.toml 文件，设置服务器地址和密钥
   ```

## 配置说明

### 服务器配置 (`linkman.toml`)

```toml
[server]
host = "0.0.0.0"  # 监听所有网络接口
port = 8388        # 服务器端口
management_port = 8389  # 管理 API 端口

[crypto]
cipher = "aes-256-gcm"  # 加密算法
key = "your-encryption-key"  # 加密密钥

[tls]
enabled = true  # 启用 TLS
cert_file = ""  # 证书文件（可选）
key_file = ""  # 私钥文件（可选）
domain = "your-domain.com"  # 域名（可选）
```

### 客户端配置 (`linkman.toml`)

```toml
[client]
local_host = "127.0.0.1"  # 本地监听地址
local_port = 1080         # 本地 SOCKS5 端口
server_host = "your-server-ip"  # 服务器 IP
server_port = 8388        # 服务器端口

[crypto]
cipher = "aes-256-gcm"  # 加密算法
key = "your-encryption-key"  # 加密密钥（必须与服务器一致）

[tls]
enabled = true  # 启用 TLS
websocket_enabled = false  # 启用 WebSocket
```

## 使用方法

### 命令行客户端

1. **启动客户端（全球模式）**
   ```bash
   source venv/bin/activate
   python -m linkman.client.main -c linkman.toml --mode global
   ```

2. **启动客户端（规则模式）**
   ```bash
   source venv/bin/activate
   python -m linkman.client.main -c linkman.toml --mode rules
   ```

3. **启动客户端（直连模式）**
   ```bash
   source venv/bin/activate
   python -m linkman.client.main -c linkman.toml --mode direct
   ```

### 图形界面

1. **启动图形界面**
   ```bash
   source venv/bin/activate
   linkman-gui
   ```

2. **使用步骤**
   - 选择代理模式（全球/规则/直连）
   - 点击 "Start VPN" 按钮启动服务
   - 客户端会自动配置系统代理
   - 点击 "Stop VPN" 按钮停止服务，系统代理会自动恢复

## 测试连接

1. **测试代理连接**
   ```bash
   curl -x socks5://127.0.0.1:1080 http://httpbin.org/ip
   ```

2. **预期结果**
   返回的 IP 应该是服务器的 IP，说明代理成功。

## 常见问题

### 1. 连接失败

**可能原因**：
- 服务器 IP 或端口配置错误
- 密钥不匹配
- 服务器防火墙阻止了连接
- 网络连接问题

**解决方案**：
- 检查服务器配置和客户端配置
- 确保服务器防火墙开放了对应端口
- 测试服务器网络连接

### 2. 代理速度慢

**可能原因**：
- 服务器网络带宽不足
- 服务器负载过高
- 网络延迟高

**解决方案**：
- 选择网络条件更好的服务器
- 优化服务器配置
- 调整加密算法（ChaCha20-Poly1305 可能在某些设备上更快）

### 3. 系统代理未自动配置

**可能原因**：
- 权限不足
- 平台不支持（目前仅支持 macOS）

**解决方案**：
- 以管理员权限运行客户端
- 手动配置系统代理

## 故障排除

### 查看客户端日志

```bash
# 查看日志文件
tail -f logs/linkman.log

# 或直接查看命令行输出
python -m linkman.client.main -c linkman.toml --mode global
```

### 查看服务器日志

```bash
# 查看系统服务日志
sudo journalctl -u linkman -f
```

### 检查网络连接

```bash
# 测试服务器连接
ping your-server-ip

# 测试端口连接
telnet your-server-ip 8388

# 检查本地代理端口
lsof -i :1080
```

## 性能优化

1. **调整缓冲区大小**
   在 `src/linkman/client/core/protocol.py` 中修改 `BUFFER_SIZE` 值。

2. **选择合适的加密算法**
   - `aes-256-gcm`：安全性高，适合高性能设备
   - `chacha20-poly1305`：速度快，适合低性能设备

3. **优化服务器网络设置**
   ```bash
   sudo sysctl -w net.core.netdev_max_backlog=4096
   sudo sysctl -w net.core.rmem_max=8388608
   sudo sysctl -w net.core.wmem_max=8388608
   ```

## 安全建议

1. **定期更换密钥**
   定期更新 `crypto.key` 以提高安全性。

2. **使用强密钥**
   密钥应该是随机生成的，长度至少 32 字节。

3. **启用 TLS**
   启用 TLS 加密可以提高流量安全性。

4. **使用 WebSocket**
   启用 WebSocket 可以更好地伪装流量。

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

如有问题，请通过 GitHub Issues 联系我们。