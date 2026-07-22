from rest_framework.permissions import BasePermission

from apps.billing.access import user_has_subscription_access


class IsTenantMember(BasePermission):
    def has_permission(self, request, view):
        return user_has_subscription_access(request.user)

    def has_object_permission(self, request, view, obj):
        return getattr(obj, "barbershop_id", None) == request.user.barbershop_id


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return bool(user_has_subscription_access(request.user) and request.user.role == "ADMIN")
