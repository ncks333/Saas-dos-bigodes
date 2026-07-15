from django.db import IntegrityError, transaction
from django.db.models import Case, Count, IntegerField, Q, Sum, Value, When
from django.utils import timezone
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from pydantic import ValidationError as PydanticValidationError
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_event
from apps.barbershops.models import Barbershop
from apps.customers.models import Customer
from apps.notifications.tasks import send_appointment_confirmation
from apps.services.models import Service
from core.security.turnstile import verify_turnstile
from core.utils.phones import brazilian_whatsapp_lookup_values
from core.utils.viewsets import TenantViewSetMixin
from .models import Appointment, ScheduleBlock
from .schemas import AvailabilityQuery, PublicBookingInput
from .serializers import AppointmentSerializer, ScheduleBlockSerializer
from .services import available_slots, cancel_with_token, create_appointment, update_appointment
from .throttles import CancellationThrottle, PublicBookingThrottle


def _get_or_create_public_customer(*, barbershop, name: str, whatsapp: str):
    canonical, legacy_local = brazilian_whatsapp_lookup_values(whatsapp)
    with transaction.atomic():
        customer = (
            Customer.objects.select_for_update()
            .filter(
                barbershop=barbershop,
                whatsapp__in=(canonical, legacy_local),
            )
            .order_by(
                Case(
                    When(whatsapp=canonical, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                ),
                "pk",
            )
            .first()
        )
        if customer is not None:
            if customer.whatsapp != canonical:
                try:
                    with transaction.atomic():
                        customer.whatsapp = canonical
                        customer.save(update_fields=["whatsapp", "updated_at"])
                except IntegrityError:
                    customer = Customer.objects.select_for_update().get(
                        barbershop=barbershop,
                        whatsapp=canonical,
                    )
            return customer, False

        try:
            with transaction.atomic():
                customer = Customer.objects.create(
                    barbershop=barbershop,
                    whatsapp=canonical,
                    name=name,
                )
        except IntegrityError:
            customer = Customer.objects.select_for_update().get(
                barbershop=barbershop,
                whatsapp=canonical,
            )
            return customer, False
        return customer, True


class AppointmentViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = Appointment.objects.select_related("customer", "service", "employee")
    serializer_class = AppointmentSerializer
    filterset_fields = ["status", "source", "starts_at"]
    ordering_fields = ["starts_at", "created_at"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        appointment, token = create_appointment(
            barbershop=request.user.barbershop,
            customer_id=serializer.validated_data["customer"].id,
            service_id=serializer.validated_data["service"].id,
            starts_at=serializer.validated_data["starts_at"],
            employee=serializer.validated_data.get("employee"),
            notes=serializer.validated_data.get("notes", ""),
            status=serializer.validated_data.get("status", Appointment.Status.PENDING),
            source=Appointment.Source.MANUAL,
        )
        record_event(request.user, "APPOINTMENT_CREATED", target=appointment, request=request)
        send_appointment_confirmation.delay(appointment.id)
        response_data = self.get_serializer(appointment).data
        response_data["cancellation_token"] = token
        return Response(response_data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        appointment = self.get_object()
        serializer = self.get_serializer(appointment, data=request.data, partial=kwargs.pop("partial", False))
        serializer.is_valid(raise_exception=True)
        appointment = update_appointment(appointment=appointment, validated_data=serializer.validated_data)
        record_event(request.user, "APPOINTMENT_UPDATED", target=appointment, request=request)
        return Response(self.get_serializer(appointment).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        appointment = self.get_object()
        if appointment.status not in [Appointment.Status.PENDING, Appointment.Status.CONFIRMED, Appointment.Status.AWAITING]:
            raise serializers.ValidationError("Este agendamento não pode ser cancelado.")
        appointment.status = Appointment.Status.CANCELLED
        appointment.save(update_fields=["status", "updated_at"])
        record_event(request.user, "APPOINTMENT_CANCELLED", target=appointment, request=request)
        return Response(self.get_serializer(appointment).data)

    @action(detail=False, methods=["get"])
    def daily_summary(self, request):
        day_field = serializers.DateField()
        day = day_field.to_internal_value(request.query_params.get("date", str(timezone.localdate())))
        qs = self.get_queryset().filter(starts_at__date=day)
        summary = qs.aggregate(
            total=Count("id"), confirmed=Count("id", filter=Q(status=Appointment.Status.CONFIRMED)),
            pending=Count("id", filter=Q(status=Appointment.Status.PENDING)),
            awaiting=Count("id", filter=Q(status=Appointment.Status.AWAITING)),
            cancelled=Count("id", filter=Q(status=Appointment.Status.CANCELLED)),
            completed=Count("id", filter=Q(status=Appointment.Status.COMPLETED)),
            no_show=Count("id", filter=Q(status=Appointment.Status.NO_SHOW)),
            revenue=Sum("service__price", filter=Q(status=Appointment.Status.COMPLETED)),
        )
        summary["revenue"] = summary["revenue"] or 0
        return Response(summary)


class ScheduleBlockViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    queryset = ScheduleBlock.objects.all()
    serializer_class = ScheduleBlockSerializer


class AvailabilityView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            query = AvailabilityQuery.model_validate(request.query_params.dict())
        except PydanticValidationError as exc:
            raise serializers.ValidationError(exc.errors())
        barbershop = Barbershop.objects.filter(slug=slug, active=True).first()
        service = Service.objects.filter(pk=query.service_id, barbershop=barbershop, active=True).first()
        if not barbershop or not service:
            raise serializers.ValidationError("Barbearia ou serviço inválido.")
        return Response({"slots": [slot.isoformat() for slot in available_slots(barbershop=barbershop, day=query.day, service=service)]})


@method_decorator(ratelimit(key="ip", rate="10/h", method="POST", block=True), name="dispatch")
class PublicBookingView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PublicBookingThrottle]

    def post(self, request, slug):
        try:
            payload = PublicBookingInput.model_validate(request.data.dict() if hasattr(request.data, "dict") else request.data)
        except PydanticValidationError as exc:
            raise serializers.ValidationError(exc.errors())
        if not verify_turnstile(payload.captcha_token, request.META.get("REMOTE_ADDR")):
            raise serializers.ValidationError("Verificação anti-bot inválida.")
        barbershop = Barbershop.objects.filter(slug=slug, active=True).first()
        if not barbershop:
            raise serializers.ValidationError("Barbearia inválida.")
        customer, _ = _get_or_create_public_customer(
            barbershop=barbershop,
            name=payload.name,
            whatsapp=payload.whatsapp,
        )
        if not customer.active:
            customer.active = True
            customer.name = payload.name
            customer.save(update_fields=["active", "name", "updated_at"])
        appointment, token = create_appointment(
            barbershop=barbershop, customer_id=customer.id, service_id=payload.service_id,
            starts_at=payload.starts_at,
            source=Appointment.Source.ONLINE, status=Appointment.Status.AWAITING,
            privacy_notice_accepted_at=timezone.now(),
        )
        send_appointment_confirmation.delay(appointment.id)
        from apps.audit.services import record_system_event
        record_system_event(
            barbershop.id,
            "PUBLIC_APPOINTMENT_CREATED",
            target=appointment,
            request=request,
            metadata={"privacy_notice_version": "2026-07-02"},
        )
        return Response({"id": appointment.id, "status": appointment.status, "cancellation_token": token}, status=status.HTTP_201_CREATED)


@method_decorator(ratelimit(key="post:token", rate="5/h", method="POST", block=True), name="dispatch")
class PublicCancellationView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [CancellationThrottle]

    def post(self, request):
        appointment = cancel_with_token(request.data.get("token", ""))
        from apps.audit.services import record_system_event
        record_system_event(appointment.barbershop_id, "PUBLIC_APPOINTMENT_CANCELLED", target=appointment, request=request)
        return Response({"id": appointment.id, "status": appointment.status})
