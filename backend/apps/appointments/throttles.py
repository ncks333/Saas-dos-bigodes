from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle
from hashlib import sha256


class PublicBookingThrottle(AnonRateThrottle):
    scope = "public_booking"


class CancellationThrottle(SimpleRateThrottle):
    scope = "cancel"
    rate = "5/hour"

    def get_cache_key(self, request, view):
        token = request.data.get("token", "missing")
        return self.cache_format % {"scope": self.scope, "ident": sha256(token.encode()).hexdigest()}
