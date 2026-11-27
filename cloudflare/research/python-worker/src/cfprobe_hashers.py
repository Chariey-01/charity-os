"""PBKDF2-SHA256 exactly as Django computes it, via the cryptography package.

The Workers Python runtime has no hashlib.pbkdf2_hmac (no OpenSSL in its
hashlib), so Django's own hasher fails. Same algorithm name, iterations and
format: hashes made by native Django verify here and the other way round.
"""
import base64

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.contrib.auth.hashers import PBKDF2PasswordHasher


class CryptographyPBKDF2PasswordHasher(PBKDF2PasswordHasher):
    def encode(self, password, salt, iterations=None):
        self._check_encode_args(password, salt)
        iterations = iterations or self.iterations
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=salt.encode(), iterations=iterations
        )
        digest = base64.b64encode(kdf.derive(password.encode())).decode("ascii").strip()
        return "%s$%d$%s$%s" % (self.algorithm, iterations, salt, digest)
