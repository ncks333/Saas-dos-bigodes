from rest_framework import generics, viewsets
from rest_framework.permissions import AllowAny
from apps.barbershops.models import Barbershop
from core.utils.viewsets import TenantViewSetMixin
from .models import Service
from .serializers import ServiceSerializer


class ServiceViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    search_fields = ["name"]
    filterset_fields = ["active"]


class PublicServiceListView(generics.ListAPIView):
    serializer_class = ServiceSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        return Service.objects.filter(barbershop__slug=self.kwargs["slug"], barbershop__active=True, active=True)
