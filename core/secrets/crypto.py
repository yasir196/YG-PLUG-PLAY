"""Windows DPAPI CurrentUser master-key protection and AES-GCM payload encryption."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecretCryptoError(RuntimeError):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[_Blob, ctypes.Array[ctypes.c_char]]:
    buf = ctypes.create_string_buffer(data)
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))), buf


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    if os.name != "nt":
        raise SecretCryptoError("DPAPI CurrentUser is available only on Windows")
    source, source_buf = _blob(data)
    output = _Blob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if protect:
        ok = fn(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output))
    else:
        ok = fn(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output))
    _ = source_buf
    if not ok:
        raise SecretCryptoError("DPAPI operation failed")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)


@dataclass(frozen=True)
class MasterKeyStore:
    path: Path

    def load_or_create(self) -> bytes:
        if self.path.exists():
            return _dpapi(self.path.read_bytes(), protect=False)
        key = AESGCM.generate_key(bit_length=256)
        protected = _dpapi(key, protect=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(protected)
        return key


class SecretCipher:
    def __init__(self, key: bytes) -> None:
        self._aes = AESGCM(key)

    def encrypt(self, plaintext: str, *, aad: bytes) -> str:
        import base64

        nonce = os.urandom(12)
        encrypted = self._aes.encrypt(nonce, plaintext.encode("utf-8"), aad)
        return base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")

    def decrypt(self, ciphertext: str, *, aad: bytes) -> str:
        import base64

        payload = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        return self._aes.decrypt(payload[:12], payload[12:], aad).decode("utf-8")
