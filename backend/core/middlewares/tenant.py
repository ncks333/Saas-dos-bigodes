from contextvars import ContextVar

current_barbershop_id: ContextVar[int | None] = ContextVar("barbershop_id", default=None)


class TenantContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        barbershop_id = getattr(getattr(request, "user", None), "barbershop_id", None)
        token = current_barbershop_id.set(barbershop_id)
        try:
            return self.get_response(request)
        finally:
            current_barbershop_id.reset(token)
