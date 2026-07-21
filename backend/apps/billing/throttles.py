from rest_framework.throttling import AnonRateThrottle


class RegularizationRequestThrottle(AnonRateThrottle):
    scope = "billing_regularization_request"


class RegularizationCheckoutThrottle(AnonRateThrottle):
    scope = "billing_regularization_checkout"
