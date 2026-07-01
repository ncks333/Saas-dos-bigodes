from django.core.cache import cache
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            marker = "healthy"
            cache.set("healthcheck", marker, timeout=10)
            if cache.get("healthcheck") != marker:
                raise RuntimeError("cache unavailable")
        except Exception:
            return Response({"status": "unavailable"}, status=503)
        return Response({"status": "ok"})
