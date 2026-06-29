from rest_framework.exceptions import PermissionDenied

from core.permissions.roles import IsTenantMember


class TenantViewSetMixin:
    permission_classes = [IsTenantMember]

    def get_queryset(self):
        return super().get_queryset().filter(barbershop_id=self.request.user.barbershop_id)

    def perform_create(self, serializer):
        if not self.request.user.barbershop_id:
            raise PermissionDenied("Usuário sem barbearia.")
        serializer.save(barbershop_id=self.request.user.barbershop_id)
