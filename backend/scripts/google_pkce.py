"""Generate ephemeral PKCE values for manual Google testing; never commit their output."""

import base64
import hashlib
import secrets

verifier = secrets.token_urlsafe(48)
challenge = (
    base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
)
print("code_verifier:", verifier)
print("code_challenge:", challenge)
