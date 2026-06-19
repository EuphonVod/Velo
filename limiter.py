
from slowapi import Limiter
from slowapi.util import get_remote_address


def _real_ip(request):
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_real_ip)
