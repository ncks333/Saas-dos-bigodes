from rest_framework.permissions import BasePermission


class IsTenantMember(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.barbershop_id)

    def has_object_permission(self, request, view, obj):
        return getattr(obj, "barbershop_id", None) == request.user.barbershop_id


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.role == "ADMIN")
