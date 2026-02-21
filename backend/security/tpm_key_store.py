"""
tpm_key_store.py — TPM / OS Hardware Key Storage (Enterprise)

Platform-specific key sealing:
  - Windows: CryptProtectData / CryptUnprotectData (DPAPI)
  - Linux:   tpm2-tools subprocess binding
  - macOS:   Keychain via 'security' CLI

Fallback: password-derived vault key (existing vault_kdf.py)

Enterprise optional — degrades gracefully to software vault.
"""

import ctypes
import logging
import os
import platform
import subprocess
import sys
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# PLATFORM DETECTION
# =============================================================================

PLATFORM = platform.system().lower()  # "windows", "linux", "darwin"


def is_tpm_available() -> bool:
    """Check if TPM/hardware key storage is available."""
    if PLATFORM == "windows":
        return _windows_dpapi_available()
    elif PLATFORM == "linux":
        return _linux_tpm_available()
    elif PLATFORM == "darwin":
        return _macos_keychain_available()
    return False


# =============================================================================
# WINDOWS — DPAPI (CryptProtectData / CryptUnprotectData)
# =============================================================================

def _windows_dpapi_available() -> bool:
    """Check if Windows DPAPI is available."""
    if PLATFORM != "windows":
        return False
    try:
        ctypes.windll.crypt32
        return True
    except (AttributeError, OSError):
        return False


class _DATA_BLOB(ctypes.Structure):
    """Windows DATA_BLOB structure for DPAPI."""
    _fields_ = [
        ("cbData", ctypes.c_ulong),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _windows_protect(data: bytes) -> Optional[bytes]:
    """Encrypt data with Windows DPAPI (CryptProtectData)."""
    if PLATFORM != "windows":
        return None
    
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        
        input_blob = _DATA_BLOB()
        input_blob.cbData = len(data)
        input_blob.pbData = ctypes.cast(
            ctypes.create_string_buffer(data, len(data)),
            ctypes.POINTER(ctypes.c_ubyte)
        )
        
        output_blob = _DATA_BLOB()
        
        result = crypt32.CryptProtectData(
            ctypes.byref(input_blob),  # pDataIn
            None,                       # szDataDescr
            None,                       # pOptionalEntropy
            None,                       # pvReserved
            None,                       # pPromptStruct
            0,                          # dwFlags
            ctypes.byref(output_blob),  # pDataOut
        )
        
        if not result:
            logger.error("[TPM] CryptProtectData failed")
            return None
        
        protected = bytes(
            (ctypes.c_ubyte * output_blob.cbData).from_address(
                ctypes.addressof(output_blob.pbData.contents)
            )
        )
        
        kernel32.LocalFree(output_blob.pbData)
        return protected
        
    except Exception as e:
        logger.error(f"[TPM] Windows DPAPI protect error: {e}")
        return None


def _windows_unprotect(data: bytes) -> Optional[bytes]:
    """Decrypt data with Windows DPAPI (CryptUnprotectData)."""
    if PLATFORM != "windows":
        return None
    
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        
        input_blob = _DATA_BLOB()
        input_blob.cbData = len(data)
        input_blob.pbData = ctypes.cast(
            ctypes.create_string_buffer(data, len(data)),
            ctypes.POINTER(ctypes.c_ubyte)
        )
        
        output_blob = _DATA_BLOB()
        
        result = crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None, None, None, None, 0,
            ctypes.byref(output_blob),
        )
        
        if not result:
            logger.error("[TPM] CryptUnprotectData failed")
            return None
        
        unprotected = bytes(
            (ctypes.c_ubyte * output_blob.cbData).from_address(
                ctypes.addressof(output_blob.pbData.contents)
            )
        )
        
        kernel32.LocalFree(output_blob.pbData)
        return unprotected
        
    except Exception as e:
        logger.error(f"[TPM] Windows DPAPI unprotect error: {e}")
        return None


# =============================================================================
# LINUX — tpm2-tools
# =============================================================================

def _linux_tpm_available() -> bool:
    """Check if tpm2-tools are available."""
    if PLATFORM != "linux":
        return False
    try:
        result = subprocess.run(
            ["tpm2_getcap", "properties-fixed"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _linux_seal(data: bytes, path: str) -> bool:
    """Seal data to TPM using tpm2-tools."""
    if PLATFORM != "linux":
        return False
    
    try:
        data_path = path + ".raw"
        sealed_path = path + ".sealed"
        
        with open(data_path, 'wb') as f:
            f.write(data)
        
        result = subprocess.run(
            ["tpm2_create", "-C", "owner",
             "-i", data_path, "-o", sealed_path,
             "-a", "fixedtpm|fixedparent|noda"],
            capture_output=True, timeout=10,
        )
        
        os.remove(data_path)  # Remove plaintext
        return result.returncode == 0
        
    except Exception as e:
        logger.error(f"[TPM] Linux TPM seal error: {e}")
        return False


def _linux_unseal(path: str) -> Optional[bytes]:
    """Unseal data from TPM."""
    if PLATFORM != "linux":
        return None
    
    try:
        sealed_path = path + ".sealed"
        out_path = path + ".unsealed"
        
        result = subprocess.run(
            ["tpm2_unseal", "-c", sealed_path, "-o", out_path],
            capture_output=True, timeout=10,
        )
        
        if result.returncode != 0:
            return None
        
        with open(out_path, 'rb') as f:
            data = f.read()
        
        os.remove(out_path)  # Remove plaintext
        return data
        
    except Exception as e:
        logger.error(f"[TPM] Linux TPM unseal error: {e}")
        return None


# =============================================================================
# MACOS — Keychain
# =============================================================================

def _macos_keychain_available() -> bool:
    """Check if macOS Keychain is available."""
    if PLATFORM != "darwin":
        return False
    try:
        result = subprocess.run(
            ["security", "list-keychains"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _macos_store(data: bytes, service: str, account: str) -> bool:
    """Store data in macOS Keychain."""
    if PLATFORM != "darwin":
        return False
    
    try:
        import base64
        encoded = base64.b64encode(data).decode('ascii')
        
        # Delete existing entry if present
        subprocess.run(
            ["security", "delete-generic-password",
             "-s", service, "-a", account],
            capture_output=True, timeout=5,
        )
        
        result = subprocess.run(
            ["security", "add-generic-password",
             "-s", service, "-a", account,
             "-w", encoded, "-U"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
        
    except Exception as e:
        logger.error(f"[TPM] macOS Keychain store error: {e}")
        return False


def _macos_retrieve(service: str, account: str) -> Optional[bytes]:
    """Retrieve data from macOS Keychain."""
    if PLATFORM != "darwin":
        return None
    
    try:
        import base64
        
        result = subprocess.run(
            ["security", "find-generic-password",
             "-s", service, "-a", account, "-w"],
            capture_output=True, timeout=5, text=True,
        )
        
        if result.returncode != 0:
            return None
        
        return base64.b64decode(result.stdout.strip())
        
    except Exception as e:
        logger.error(f"[TPM] macOS Keychain retrieve error: {e}")
        return None


# =============================================================================
# UNIFIED PUBLIC API
# =============================================================================

def store_vault_key(key: bytes) -> Tuple[bool, str]:
    """Store vault master key in hardware key storage.
    
    Tries platform-specific TPM/key store first.
    Falls back to password-derived vault (existing).
    
    Args:
        key: 32-byte vault master key.
    
    Returns:
        Tuple of (success, method_used).
    """
    if PLATFORM == "windows" and _windows_dpapi_available():
        protected = _windows_protect(key)
        if protected:
            # Save DPAPI blob to file
            path = os.path.join('secure_data', 'vault_key.dpapi')
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(protected)
            logger.info("[TPM] Vault key stored via Windows DPAPI")
            return True, "windows_dpapi"
    
    elif PLATFORM == "linux" and _linux_tpm_available():
        path = os.path.join('secure_data', 'vault_key')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if _linux_seal(key, path):
            logger.info("[TPM] Vault key sealed to TPM")
            return True, "linux_tpm"
    
    elif PLATFORM == "darwin" and _macos_keychain_available():
        if _macos_store(key, "YGB_Vault", "master_key"):
            logger.info("[TPM] Vault key stored in macOS Keychain")
            return True, "macos_keychain"
    
    logger.info("[TPM] No hardware key store available — using software vault")
    return False, "software_fallback"


def retrieve_vault_key() -> Tuple[Optional[bytes], str]:
    """Retrieve vault master key from hardware key storage.
    
    Returns:
        Tuple of (key_bytes_or_None, method_used).
    """
    if PLATFORM == "windows" and _windows_dpapi_available():
        path = os.path.join('secure_data', 'vault_key.dpapi')
        if os.path.exists(path):
            with open(path, 'rb') as f:
                protected = f.read()
            key = _windows_unprotect(protected)
            if key:
                return key, "windows_dpapi"
    
    elif PLATFORM == "linux" and _linux_tpm_available():
        path = os.path.join('secure_data', 'vault_key')
        key = _linux_unseal(path)
        if key:
            return key, "linux_tpm"
    
    elif PLATFORM == "darwin" and _macos_keychain_available():
        key = _macos_retrieve("YGB_Vault", "master_key")
        if key:
            return key, "macos_keychain"
    
    return None, "software_fallback"
