from django.db.models import Count, Sum
from django.db.models.functions import ExtractHour
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.appointments.models import Appointment
from apps.billing.models import Subscription
from core.permissions.roles import IsTenantMember


class DashboardView(APIView):
    permission_classes = [IsTenantMember]

    def get(self, request):
        today = timezone.localdate()
        month_start = today.replace(day=1)
        qs = Appointment.objects.filter(barbershop_id=request.user.barbershop_id)
        completed = qs.filter(status=Appointment.Status.COMPLETED)
        subscription = Subscription.objects.filter(
            barbershop_id=request.user.barbershop_id
        ).only("status", "trial_ends_at").first()
        total = qs.count()
        cancelled = qs.filter(status=Appointment.Status.CANCELLED).count()
        popular_hours = list(qs.annotate(hour=ExtractHour("starts_at")).values("hour").annotate(total=Count("id")).order_by("-total")[:5])
        recurring = qs.values("customer_id", "customer__name").annotate(total=Count("id")).filter(total__gt=1).order_by("-total")[:10]
        return Response({
            "daily_revenue": completed.filter(starts_at__date=today).aggregate(value=Sum("service__price"))["value"] or 0,
            "monthly_revenue": completed.filter(starts_at__date__gte=month_start).aggregate(value=Sum("service__price"))["value"] or 0,
            "appointments": total,
            "cancellation_rate": round(cancelled * 100 / total, 2) if total else 0,
            "popular_hours": popular_hours,
            "recurring_customers": list(recurring),
            "subscription_status": subscription.status if subscription else None,
            "trial_ends_at": subscription.trial_ends_at if subscription else None,
        })
