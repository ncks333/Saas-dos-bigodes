from rest_framework import viewsets
from apps.audit.services import record_event
from core.utils.viewsets import TenantViewSetMixin
from .models import Customer
from .serializers import CustomerSerializer


class CustomerViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    search_fields = ["name", "whatsapp"]
    filterset_fields = ["active"]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        record_event(self.request.user, "CUSTOMER_CREATED", target=serializer.instance, request=self.request)

    def perform_destroy(self, instance):
        instance.active = False
        instance.save(update_fields=["active", "updated_at"])
        record_event(self.request.user, "CUSTOMER_SOFT_DELETED", target=instance, request=self.request)
