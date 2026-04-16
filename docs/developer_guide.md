# LinkMan VPN Developer Guide

This guide provides detailed information for developers working on the LinkMan VPN project.

## Architecture Overview

LinkMan VPN is designed with a modular architecture that separates concerns and allows for easy extension.

### Core Components

1. **Protocol Layer**
   - Abstract protocol base classes
   - Protocol implementations (Shadowsocks 2022, etc.)
   - Protocol manager for registration and creation

2. **Transport Layer**
   - TCP transport
   - TLS encryption
   - WebSocket support

3. **Encryption Layer**
   - AEAD ciphers
   - Key management
   - Secure key storage

4. **Connection Management**
   - Connection pooling
   - Health checking
   - Connection lifecycle management

5. **Monitoring**
   - Metrics collection
   - Alerting
   - Logging

## Getting Started

### Setting Up the Development Environment

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/linkman.git
   cd linkman
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install development dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -e .[dev]
   ```

### Running Tests

```bash
pytest tests/ -v
```

### Code Style

LinkMan follows PEP 8 code style guidelines. Use the following tools to ensure code quality:

- **Black**: Code formatter
  ```bash
  black src/
  ```

- **Flake8**: Linter
  ```bash
  flake8 src/
  ```

- **Mypy**: Type checker
  ```bash
  mypy src/
  ```

## API Reference

### Protocol Layer

#### ProtocolBase

Base abstract class for all client-side protocols.

```python
from linkman.shared.protocol.abstract import ProtocolBase

class MyProtocol(ProtocolBase):
    async def connect(self, server_host, server_port, target, max_retries=3, retry_delay=2.0):
        # Implementation
        pass
    
    async def relay(self, local_reader, local_writer):
        # Implementation
        pass
    
    async def close(self):
        # Implementation
        pass
    
    @property
    def is_connected(self):
        # Implementation
        pass
    
    @property
    def bytes_sent(self):
        # Implementation
        pass
    
    @property
    def bytes_received(self):
        # Implementation
        pass
```

#### ServerProtocolBase

Base abstract class for all server-side protocols.

```python
from linkman.shared.protocol.abstract import ServerProtocolBase

class MyServerProtocol(ServerProtocolBase):
    async def handle(self):
        # Implementation
        pass
    
    async def close(self):
        # Implementation
        pass
    
    @property
    def client_address(self):
        # Implementation
        pass
    
    @property
    def target_address(self):
        # Implementation
        pass
    
    @property
    def bytes_sent(self):
        # Implementation
        pass
    
    @property
    def bytes_received(self):
        # Implementation
        pass
```

#### ProtocolFactory

Abstract factory for creating protocol instances.

```python
from linkman.shared.protocol.abstract import ProtocolFactory

class MyProtocolFactory(ProtocolFactory):
    def create_client_protocol(self, **kwargs):
        # Implementation
        pass
    
    def create_server_protocol(self, reader, writer, handler, **kwargs):
        # Implementation
        pass
```

### Key Management

#### KeyManager

Basic key management for encryption keys.

```python
from linkman.shared.crypto.keys import KeyManager

# Create a key manager with a generated master key
key_manager = KeyManager()

# Create a key manager from an existing key
key_manager = KeyManager(master_key=b'my-secret-key')

# Derive a subkey
subkey = key_manager.derive_subkey(salt=b'salt', length=32)

# Generate a session key
session_key = key_manager.generate_session_key('session-id')
```

#### SecureKeyManager

Enhanced key management with additional security features.

```python
from linkman.shared.crypto.secure_keys import get_secure_key_manager

# Get the secure key manager
secure_key_manager = get_secure_key_manager(storage_path='keys.json')

# Generate a key for encryption
key_id = secure_key_manager.generate_key(usage='encryption')

# Get the active key
key_id, key = secure_key_manager.get_key(usage='encryption')

# Rotate a key
new_key_id = secure_key_manager.rotate_key(usage='encryption')
```

### Connection Pooling

#### ConnectionPool

Manages and reuses connections for better performance.

```python
from linkman.shared.utils.connection_pool import ConnectionPool

async def create_connection():
    # Implementation to create a connection
    reader, writer = await asyncio.open_connection('example.com', 80)
    return reader, writer

# Create a connection pool
pool = ConnectionPool(
    create_connection=create_connection,
    max_connections=100,
    max_idle_time=300.0,
    health_check_interval=60.0,
)

# Start the pool
await pool.start()

# Get a connection
conn = await pool.get_connection()

# Use the connection
# ...

# Return the connection to the pool
await pool.return_connection(conn)

# Stop the pool
await pool.stop()
```

### Health Checking

#### HealthChecker

Monitors server health and availability.

```python
from linkman.shared.utils.health_check import HealthChecker

# Create a health checker
checker = HealthChecker(
    check_interval=30.0,
    timeout=5.0,
    max_consecutive_failures=3,
)

# Add a server to monitor
checker.add_server('example.com', 80, check_type='http')

# Start the health checker
await checker.start()

# Get server status
status = checker.get_server_status('example.com', 80)
print(f"Server status: {status.is_healthy}")

# Stop the health checker
await checker.stop()
```

### Monitoring

#### MetricsCollector

Collects system and application metrics.

```python
from linkman.shared.utils.monitoring import get_monitoring_manager

# Get the monitoring manager
monitoring = get_monitoring_manager()

# Get the metrics collector
collector = monitoring.get_collector()

# Add a metric
collector.add_metric('custom.metric', 42.0, tag1='value1', tag2='value2')

# Start monitoring
await monitoring.start()

# Stop monitoring
await monitoring.stop()
```

## Extending LinkMan

### Adding a New Protocol

1. **Create a protocol implementation**:
   ```python
   from linkman.shared.protocol.abstract import ProtocolBase, ServerProtocolBase

   class MyProtocol(ProtocolBase):
       # Implementation
       pass

   class MyServerProtocol(ServerProtocolBase):
       # Implementation
       pass
   ```

2. **Create a protocol factory**:
   ```python
   from linkman.shared.protocol.abstract import ProtocolFactory

   class MyProtocolFactory(ProtocolFactory):
       def create_client_protocol(self, **kwargs):
           return MyProtocol(**kwargs)
       
       def create_server_protocol(self, reader, writer, handler, **kwargs):
           return MyServerProtocol(reader, writer, handler, **kwargs)
   ```

3. **Register the protocol**:
   ```python
   from linkman.shared.protocol.manager import protocol_manager

   protocol_manager.register_protocol('my-protocol', MyProtocolFactory())
   ```

### Adding a New Transport

1. **Create a transport implementation**:
   ```python
   class MyTransport:
       # Implementation
       pass
   ```

2. **Integrate with the protocol**:
   ```python
   class MyProtocol(ProtocolBase):
       def __init__(self, transport=None, **kwargs):
           self._transport = transport or MyTransport()
           # Other initialization
   ```

### Adding a New Encryption Algorithm

1. **Implement the cipher**:
   ```python
   from linkman.shared.crypto.aead import AEADCipher

   class MyCipher(AEADCipher):
       # Implementation
       pass
   ```

2. **Register the cipher**:
   ```python
   from linkman.shared.crypto.aead import AEADType, cipher_registry

   cipher_registry[AEADType.MY_CIPHER] = MyCipher
   ```

## Best Practices

### Code Organization

- **Modular design**: Keep components small and focused
- **Separation of concerns**: Each component should have a single responsibility
- **Abstraction**: Use abstract base classes to define interfaces
- **Dependency injection**: Pass dependencies instead of hardcoding them

### Security

- **Encryption**: Use only secure encryption algorithms
- **Key management**: Follow best practices for key generation and storage
- **Input validation**: Validate all user input
- **Error handling**: Don't expose sensitive information in error messages

### Performance

- **Async IO**: Use asyncio for non-blocking operations
- **Buffer management**: Optimize buffer sizes for different network conditions
- **Connection pooling**: Reuse connections when possible
- **Resource management**: Clean up resources properly

### Testing

- **Unit tests**: Test individual components in isolation
- **Integration tests**: Test interactions between components
- **End-to-end tests**: Test the complete system
- **Performance tests**: Test under realistic load

## Troubleshooting

### Common Issues

1. **Connection failures**
   - Check network connectivity
   - Verify server address and port
   - Check firewall settings
   - Examine logs for error messages

2. **Performance issues**
   - Monitor system resources
   - Check network latency
   - Adjust buffer sizes
   - Use connection pooling

3. **Security issues**
   - Rotate encryption keys regularly
   - Use strong encryption algorithms
   - Monitor for unusual traffic patterns
   - Keep software up to date

### Debugging Tips

- **Enable debug logging**:
  ```bash
  linkman-client start --config config.json --debug
  ```

- **Monitor metrics**:
  Check the metrics exported to JSON files in the `metrics/` directory

- **Use a network analyzer**:
  Tools like Wireshark can help diagnose network issues

## Contributing

### Pull Request Process

1. **Fork the repository**
2. **Create a feature branch**
3. **Make your changes**
4. **Run tests**
5. **Submit a Pull Request**

### Code Review Guidelines

- **Code quality**: Follow PEP 8 and project conventions
- **Test coverage**: Add tests for new functionality
- **Documentation**: Update documentation for changes
- **Security**: Consider security implications of changes

### Release Process

1. **Update version number** in `setup.py`
2. **Update CHANGELOG.md** with new features and fixes
3. **Run all tests** to ensure nothing is broken
4. **Create a release tag**
5. **Publish to PyPI**

## Conclusion

LinkMan VPN is designed to be a flexible, secure, and high-performance VPN solution. By following this guide, you can effectively develop and extend the project to meet your needs.

If you have any questions or need further assistance, please reach out to the community through the forums or Discord channel.
