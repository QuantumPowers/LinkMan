# LinkMan VPN

LinkMan is a high-performance, secure VPN implementation based on Shadowsocks 2022 protocol.

## Features

- **High Performance**: Optimized async IO and buffer management for maximum throughput
- **Secure**: Implements Shadowsocks 2022 protocol with AEAD encryption
- **Flexible**: Supports multiple protocols and transport methods
- **Reliable**: Connection pooling and health checking for improved reliability
- **Monitorable**: Comprehensive metrics collection and monitoring
- **Extensible**: Modular architecture for easy extension

## Architecture

LinkMan consists of the following components:

- **Client**: Local proxy that handles connections from applications
- **Server**: Remote server that forwards connections to target destinations
- **Shared**: Common code used by both client and server

### Protocol Stack

1. **Application Layer**: SOCKS5 proxy interface for applications
2. **Protocol Layer**: Shadowsocks 2022 protocol implementation
3. **Transport Layer**: TCP, TLS, and WebSocket support
4. **Encryption Layer**: AEAD encryption with various algorithms

## Installation

### Prerequisites

- Python 3.11+
- pip

### Install from Source

```bash
# Clone the repository
git clone https://github.com/yourusername/linkman.git
cd linkman

# Install dependencies
pip install -r requirements.txt

# Install the package
pip install -e .
```

### Install from PyPI

```bash
pip install linkman-vpn
```

## Usage

### Server Setup

1. **Generate a master key**:
   ```bash
   linkman-server generate-key
   ```

2. **Create a configuration file** (`linkman.toml`):
   ```toml
   [server]
   host = "0.0.0.0"
   port = 8388

   [crypto]
   key = "your-master-key-here"
   cipher = "aes-256-gcm"

   [tls]
   enabled = true
   cert_file = "server.crt"
   key_file = "server.key"
   websocket_enabled = true
   websocket_path = "/linkman"
   ```

3. **Start the server**:
   ```bash
   linkman-server -c linkman.toml
   ```

### Client Setup

1. **Create a configuration file** (`linkman.toml`):
   ```toml
   [client]
   local_host = "127.0.0.1"
   local_port = 1080
   server_host = "your-server-ip"
   server_port = 8388

   [crypto]
   key = "your-master-key-here"
   cipher = "aes-256-gcm"

   [tls]
   enabled = true
   websocket_enabled = true
   websocket_path = "/linkman"
   ```

2. **Start the client**:
   ```bash
   linkman-client -c linkman.toml
   ```

### Configuration Options

#### Server Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `server.host` | Server hostname or IP | "0.0.0.0" |
| `server.port` | Server port | 8388 |
| `crypto.key` | Master encryption key | - |
| `crypto.cipher` | Encryption algorithm | "aes-256-gcm" |
| `tls.enabled` | Enable TLS | false |
| `tls.cert_file` | TLS certificate file | "" |
| `tls.key_file` | TLS private key file | "" |
| `tls.websocket_enabled` | Enable WebSocket | false |
| `tls.websocket_path` | WebSocket path | "/linkman" |

#### Client Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `client.local_host` | Local proxy host | "127.0.0.1" |
| `client.local_port` | Local proxy port | 1080 |
| `client.server_host` | Server hostname or IP | - |
| `client.server_port` | Server port | 8388 |
| `crypto.key` | Master encryption key | - |
| `crypto.cipher` | Encryption algorithm | "aes-256-gcm" |
| `tls.enabled` | Enable TLS | false |
| `tls.websocket_enabled` | Enable WebSocket | false |
| `tls.websocket_path` | WebSocket path | "/linkman" |

## Advanced Features

### Connection Pooling

LinkMan uses connection pooling to improve performance and reduce connection overhead. The connection pool automatically manages and reuses connections, providing better performance for high-traffic scenarios.

### Health Checking

LinkMan includes a health checking system that monitors server availability and performance. It can automatically detect and handle server failures, providing better reliability.

### Monitoring

LinkMan provides comprehensive metrics collection and monitoring capabilities, including:

- System metrics (CPU, memory, network)
- Application metrics (connections, traffic, latency)
- Alerting based on thresholds

### Key Management

LinkMan includes a secure key management system that supports:

- Key rotation
- Key expiration
- Encrypted key storage
- Key usage auditing

## Development

### Directory Structure

```
linkman/
├── src/
│   ├── linkman/
│   │   ├── client/          # Client-side code
│   │   ├── server/          # Server-side code
│   │   ├── shared/          # Shared code
│   │   └── __init__.py
├── tests/                   # Test files
├── requirements.txt         # Dependencies
├── setup.py                 # Package setup
└── README.md                # This file
```

### Running Tests

```bash
pytest tests/
```

### Code Style

LinkMan follows PEP 8 code style guidelines. Use `black` and `flake8` to ensure code quality:

```bash
black src/
flake8 src/
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Workflow

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a Pull Request

## License

LinkMan is licensed under the MIT License. See the `LICENSE` file for details.

## Security

### Security Features

- AEAD encryption for all traffic
- Perfect forward secrecy
- TLS encryption for transport
- WebSocket support for obfuscation
- Secure key management

### Reporting Security Issues

If you discover a security issue, please email security@linkman-vpn.com instead of opening an issue.

## Support

### Documentation

- [User Guide](docs/user_guide.md)
- [Developer Guide](docs/developer_guide.md)
- [API Reference](docs/api_reference.md)

### Community

- [GitHub Issues](https://github.com/yourusername/linkman/issues)
- [Discord](https://discord.gg/linkman)
- [Forum](https://forum.linkman-vpn.com)

## Acknowledgments

LinkMan is based on the Shadowsocks 2022 protocol specification and draws inspiration from various open-source VPN implementations.

## Roadmap

### Upcoming Features

- [ ] WireGuard protocol support
- [ ] IPsec protocol support
- [ ] Multi-platform GUI
- [ ] Mobile apps (iOS, Android)
- [ ] Cloud deployment tools
- [ ] Advanced routing rules
- [ ] Traffic analysis and optimization
- [ ] Integration with popular authentication providers
