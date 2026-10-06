"""Small, database-independent primitives for password and session secrets."""
import hashlib
import hmac
import secrets


class ScryptPasswordHasher:
    """Use Python's scrypt implementation with a fresh random salt per password."""

    _n = 1 << 14
    _r = 8
    _p = 1
    _salt_bytes = 16
    _key_bytes = 32

    def hash(self, password: str) -> str:
        salt = secrets.token_bytes(self._salt_bytes)
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=self._n, r=self._r,
            p=self._p, dklen=self._key_bytes,
        )
        return f"scrypt${self._n}${self._r}${self._p}${salt.hex()}${digest.hex()}"

    def verify(self, password: str, encoded_hash: str) -> bool:
        try:
            algorithm, n, r, p, salt_hex, digest_hex = encoded_hash.split("$", 5)
            if (algorithm != "scrypt" or int(n) != self._n or int(r) != self._r
                    or int(p) != self._p):
                return False
            salt, expected = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
            if len(salt) != self._salt_bytes or len(expected) != self._key_bytes:
                return False
            actual = hashlib.scrypt(
                password.encode("utf-8"), salt=salt, n=int(n), r=int(r),
                p=int(p), dklen=len(expected),
            )
        except (ValueError, TypeError, MemoryError):
            return False
        return hmac.compare_digest(actual, expected)


class SessionStore:
    """Opaque session tokens are only persisted as SHA-256 digests."""

    @staticmethod
    def new_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
