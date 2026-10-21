from slowapi import Limiter
from slowapi.util import get_remote_address

# Local-development limiter. Use a shared store or gateway limit in production.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
)