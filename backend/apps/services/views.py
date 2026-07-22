from rest_framework import generics, viewsets
from rest_framework.permissions import AllowAny
from apps.barbershops.models import Barbershop
from apps.billing.access import barbershops_with_access
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
        barbershops = barbershops_with_access(
            Barbershop.objects.filter(slug=self.kwargs["slug"], active=True)
        )
        return Service.objects.filter(barbershop__in=barbershops, active=True)
