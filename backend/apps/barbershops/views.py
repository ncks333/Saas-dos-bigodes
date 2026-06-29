from rest_framework import generics, viewsets
from rest_framework.permissions import AllowAny

from core.permissions.roles import IsAdminRole
from apps.audit.services import record_event
from .models import Barbershop, OperatingHour
from .serializers import BarbershopSerializer, OperatingHourSerializer


class CurrentBarbershopView(generics.RetrieveUpdateAPIView):
    serializer_class = BarbershopSerializer
    permission_classes = [IsAdminRole]

    def get_object(self):
        return self.request.user.barbershop

    def perform_update(self, serializer):
        serializer.save()
        record_event(self.request.user, "BARBERSHOP_SETTINGS_CHANGED", target=serializer.instance, request=self.request)


class OperatingHourViewSet(viewsets.ModelViewSet):
    serializer_class = OperatingHourSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        return OperatingHour.objects.filter(barbershop_id=self.request.user.barbershop_id)

    def perform_create(self, serializer):
        serializer.save(barbershop_id=self.request.user.barbershop_id)


class PublicBarbershopView(generics.RetrieveAPIView):
    queryset = Barbershop.objects.filter(active=True)
    serializer_class = BarbershopSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"
