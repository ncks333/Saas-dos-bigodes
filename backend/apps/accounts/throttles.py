from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    scope = "login"

    def parse_rate(self, rate):
        return 5, 15 * 60
