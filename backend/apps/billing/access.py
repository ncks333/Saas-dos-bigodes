from apps.billing.models import Subscription


def user_has_subscription_access(user) -> bool:
    if not getattr(user, "is_authenticated", False) or not user.barbershop_id:
        return False
    return Subscription.objects.filter(
        barbershop_id=user.barbershop_id,
        status__in=Subscription.allowed_statuses(),
    ).exists()


def barbershops_with_access(queryset):
    return queryset.filter(subscription__status__in=Subscription.allowed_statuses())
