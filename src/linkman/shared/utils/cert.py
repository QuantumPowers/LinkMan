"""
TLS certificate generation and management utilities.

Provides functions for:
- Generating self-signed TLS certificates
- Loading and validating TLS certificates
- Managing certificate files
"""

from __future__ import annotations

import os
import ssl
from datetime import datetime, timedelta
from typing import Tuple

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.backends import default_backend

from linkman.shared.utils.logger import get_logger

logger = get_logger("cert")


def generate_self_signed_cert(
    domain: str = "localhost",
    validity_days: int = 365,
    key_size: int = 2048,
) -> Tuple[bytes, bytes]:
    """
    Generate a self-signed TLS certificate.

    Args:
        domain: Domain name for the certificate
        validity_days: Number of days the certificate is valid
        key_size: RSA key size in bits

    Returns:
        Tuple of (private_key_pem, certificate_pem)
    """
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend(),
    )

    # Generate public key
    public_key = private_key.public_key()

    # Build subject and issuer
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "LinkMan VPN"),
        x509.NameAttribute(NameOID.COMMON_NAME, domain),
    ])

    # Build certificate
    builder = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        public_key
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.utcnow()
    ).not_valid_after(
        datetime.utcnow() + timedelta(days=validity_days)
    ).add_extension(
        x509.SubjectAlternativeName([x509.DNSName(domain)]),
        critical=False,
    )

    # Sign the certificate
    certificate = builder.sign(
        private_key=private_key,
        algorithm=hashes.SHA256(),
        backend=default_backend(),
    )

    # Serialize private key and certificate
    private_key_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=NoEncryption(),
    )

    certificate_pem = certificate.public_bytes(Encoding.PEM)

    return private_key_pem, certificate_pem


def save_cert_files(
    private_key_pem: bytes,
    certificate_pem: bytes,
    cert_dir: str = ".",
    domain: str = "localhost",
) -> Tuple[str, str]:
    """
    Save certificate files to disk.

    Args:
        private_key_pem: Private key in PEM format
        certificate_pem: Certificate in PEM format
        cert_dir: Directory to save files
        domain: Domain name for filename

    Returns:
        Tuple of (cert_file_path, key_file_path)
    """
    # Create directory if it doesn't exist
    os.makedirs(cert_dir, exist_ok=True)

    # Generate filenames
    cert_filename = f"{domain}.crt"
    key_filename = f"{domain}.key"

    cert_path = os.path.join(cert_dir, cert_filename)
    key_path = os.path.join(cert_dir, key_filename)

    # Save files
    with open(cert_path, "wb") as f:
        f.write(certificate_pem)

    with open(key_path, "wb") as f:
        f.write(private_key_pem)

    # Set proper permissions for key file
    os.chmod(key_path, 0o600)

    logger.info(f"Certificate saved to {cert_path}")
    logger.info(f"Private key saved to {key_path}")

    return cert_path, key_path


def load_cert_files(
    cert_file: str,
    key_file: str,
) -> Tuple[ssl.SSLContext, bool]:
    """
    Load certificate files and create SSL context.

    Args:
        cert_file: Path to certificate file
        key_file: Path to private key file

    Returns:
        Tuple of (ssl_context, is_valid)
    """
    try:
        # Check if files exist
        if not os.path.exists(cert_file):
            logger.error(f"Certificate file not found: {cert_file}")
            return None, False

        if not os.path.exists(key_file):
            logger.error(f"Private key file not found: {key_file}")
            return None, False

        # Create SSL context
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile=cert_file, keyfile=key_file)

        logger.info(f"Loaded certificate from {cert_file}")
        return context, True

    except Exception as e:
        logger.error(f"Error loading certificate files: {e}")
        return None, False


def validate_cert(cert_file: str) -> bool:
    """
    Validate a certificate file.

    Args:
        cert_file: Path to certificate file

    Returns:
        True if certificate is valid, False otherwise
    """
    try:
        with open(cert_file, "rb") as f:
            cert_data = f.read()

        certificate = load_pem_x509_certificate(cert_data, default_backend())

        # Check if certificate is expired
        now = datetime.utcnow()
        if now < certificate.not_valid_before:
            logger.error("Certificate is not yet valid")
            return False

        if now > certificate.not_valid_after:
            logger.error("Certificate has expired")
            return False

        logger.info("Certificate is valid")
        return True

    except Exception as e:
        logger.error(f"Error validating certificate: {e}")
        return False


def get_cert_info(cert_file: str) -> dict:
    """
    Get certificate information.

    Args:
        cert_file: Path to certificate file

    Returns:
        Dictionary with certificate information
    """
    try:
        with open(cert_file, "rb") as f:
            cert_data = f.read()

        certificate = load_pem_x509_certificate(cert_data, default_backend())

        info = {
            "subject": certificate.subject.rfc4514_string(),
            "issuer": certificate.issuer.rfc4514_string(),
            "serial_number": certificate.serial_number,
            "not_valid_before": certificate.not_valid_before.isoformat(),
            "not_valid_after": certificate.not_valid_after.isoformat(),
            "public_key_algorithm": certificate.public_key()._backend._key.curve.name if hasattr(certificate.public_key(), "_backend") else "RSA",
        }

        return info

    except Exception as e:
        logger.error(f"Error getting certificate info: {e}")
        return {}


def generate_cert_if_missing(
    domain: str = "localhost",
    cert_dir: str = ".",
    validity_days: int = 365,
) -> Tuple[str, str, bool]:
    """
    Generate certificate if it doesn't exist.

    Args:
        domain: Domain name for certificate
        cert_dir: Directory to save files
        validity_days: Number of days the certificate is valid

    Returns:
        Tuple of (cert_file_path, key_file_path, was_generated)
    """
    cert_path = os.path.join(cert_dir, f"{domain}.crt")
    key_path = os.path.join(cert_dir, f"{domain}.key")

    # Check if files exist and are valid
    if os.path.exists(cert_path) and os.path.exists(key_path):
        if validate_cert(cert_path):
            logger.info("Using existing valid certificate")
            return cert_path, key_path, False
        else:
            logger.warning("Existing certificate is invalid, generating new one")

    # Generate new certificate
    private_key_pem, certificate_pem = generate_self_signed_cert(
        domain=domain,
        validity_days=validity_days,
    )

    cert_path, key_path = save_cert_files(
        private_key_pem,
        certificate_pem,
        cert_dir=cert_dir,
        domain=domain,
    )

    return cert_path, key_path, True
