# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""AES-256-GCM encrypted API key vault (P3 Task 1.6).

Vault file: /captain/vault/keys.vault
Format: 12-byte nonce + ciphertext + 16-byte tag, all base64 encoded per entry.
Master key derived from VAULT_MASTER_KEY env var via PBKDF2.
"""

import os
import json
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


VAULT_PATH = os.environ.get("VAULT_KEY_PATH", "/captain/vault/keys.vault")
VAULT_SALT = b"captain-vault-salt-v1"  # Fixed salt; key uniqueness from master key


def _derive_key(master_key: str) -> bytes:
    """Derive a 256-bit AES key from the master key string."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=VAULT_SALT,
        iterations=600_000,
    )
    return kdf.derive(master_key.encode())


def _get_aesgcm() -> AESGCM:
    """Get AESGCM cipher from environment master key."""
    master_key = os.environ.get("VAULT_MASTER_KEY")
    if not master_key:
        raise RuntimeError("VAULT_MASTER_KEY environment variable not set")
    return AESGCM(_derive_key(master_key))


def load_vault() -> dict:
    """Load and decrypt the vault. Returns empty dict if vault doesn't exist."""
    if not os.path.exists(VAULT_PATH):
        return {}
    with open(VAULT_PATH, "rb") as f:
        raw = f.read()
    if not raw:
        return {}
    aesgcm = _get_aesgcm()
    nonce = raw[:12]
    ciphertext = raw[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return json.loads(plaintext.decode())


def save_vault(data: dict):
    """Encrypt and save the vault."""
    aesgcm = _get_aesgcm()
    nonce = os.urandom(12)
    plaintext = json.dumps(data).encode()
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    os.makedirs(os.path.dirname(VAULT_PATH), exist_ok=True)
    with open(VAULT_PATH, "wb") as f:
        f.write(nonce + ciphertext)


def get_api_key(account_id: str) -> str | None:
    """Retrieve an API key for an account."""
    vault = load_vault()
    return vault.get(account_id)


def store_api_key(account_id: str, api_key: str):
    """Store an API key for an account."""
    vault = load_vault()
    vault[account_id] = api_key
    save_vault(vault)
