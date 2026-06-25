import base64
import hashlib
import secrets


PBKDF2_MIN_ITERATIONS = 600_000


def hash_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(value: str, iterations: int = PBKDF2_MIN_ITERATIONS) -> str:
    if (
        isinstance(iterations, bool)
        or not isinstance(iterations, int)
        or iterations < PBKDF2_MIN_ITERATIONS
    ):
        raise ValueError(
            f"iterations must be an integer of at least {PBKDF2_MIN_ITERATIONS}"
        )

    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        value.encode("utf-8"),
        salt,
        iterations,
    )
    encoded_salt = base64.urlsafe_b64encode(salt).decode("ascii")
    encoded_digest = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256${iterations}${encoded_salt}${encoded_digest}"


def secure_equals(left: str, right: str) -> bool:
    return secrets.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
