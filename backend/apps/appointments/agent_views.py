from datetime import datetime
from zoneinfo import ZoneInfo

from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.services import record_event
from apps.customers.models import Customer
from apps.notifications.tasks import send_appointment_confirmation
from apps.services.models import Service
from core.permissions.roles import IsTenantMember
from .agent_serializers import (
    AvailabilityToolSerializer,
    CancelReservationToolSerializer,
    CreateReservationToolSerializer,
    UserReservationsToolSerializer,
)
from .models import Appointment
from .services import (
    active_appointments_for_day,
    available_slots,
    cancel_appointment,
    create_appointment,
)


class AgentToolViewSet(viewsets.ViewSet):
    permission_classes = [IsTenantMember]

    def _customer(self, request, customer_id: int) -> Customer:
        customer = Customer.objects.filter(
            pk=customer_id,
            barbershop_id=request.user.barbershop_id,
            active=True,
        ).first()
        if not customer:
            raise serializers.ValidationError("Usuário inválido para esta barbearia.")
        return customer

    def _service(self, request, service_id: int) -> Service:
        service = Service.objects.filter(
            pk=service_id,
            barbershop_id=request.user.barbershop_id,
            active=True,
        ).first()
        if not service:
            raise serializers.ValidationError("Serviço inválido para esta barbearia.")
        return service

    @action(detail=False, methods=["post"], url_path="consultar-disponibilidade")
    def consultar_disponibilidade(self, request):
        serializer = AvailabilityToolSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = self._service(request, serializer.validated_data["servico_id"])
        slots = available_slots(
            barbershop=request.user.barbershop,
            day=serializer.validated_data["data"],
            service=service,
        )
        return Response({"horarios": [slot.isoformat() for slot in slots]})

    @action(detail=False, methods=["post"], url_path="listar-reservas-usuario")
    def listar_reservas_usuario(self, request):
        serializer = UserReservationsToolSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = self._customer(request, serializer.validated_data["usuario_id"])
        reservations = active_appointments_for_day(
            barbershop=request.user.barbershop,
            customer_id=customer.id,
            day=serializer.validated_data["data"],
        )
        return Response({
            "reservas": [
                {
                    "reserva_id": item.id,
                    "horario": item.starts_at.astimezone(
                        ZoneInfo(request.user.barbershop.timezone)
                    ).strftime("%H:%M"),
                    "status": item.status,
                }
                for item in reservations
            ]
        })

    @action(detail=False, methods=["post"], url_path="criar-reserva")
    def criar_reserva(self, request):
        serializer = CreateReservationToolSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        customer = self._customer(request, data["usuario_id"])
        service = self._service(request, data["servico_id"])
        starts_at = datetime.combine(
            data["data"], data["horario"], tzinfo=ZoneInfo(request.user.barbershop.timezone)
        )
        appointment, _ = create_appointment(
            barbershop=request.user.barbershop,
            customer_id=customer.id,
            service_id=service.id,
            starts_at=starts_at,
            source=Appointment.Source.ONLINE,
            status=Appointment.Status.AWAITING,
        )
        record_event(request.user, "AGENT_APPOINTMENT_CREATED", target=appointment, request=request)
        send_appointment_confirmation.delay(appointment.id)
        return Response(
            {"reserva_id": appointment.id, "status": appointment.status},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="cancelar-reserva")
    def cancelar_reserva(self, request):
        serializer = CancelReservationToolSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        appointment = Appointment.objects.filter(
            pk=serializer.validated_data["reserva_id"],
            barbershop_id=request.user.barbershop_id,
        ).first()
        if not appointment:
            raise serializers.ValidationError("Reserva não encontrada.")
        appointment = cancel_appointment(appointment=appointment)
        record_event(request.user, "AGENT_APPOINTMENT_CANCELLED", target=appointment, request=request)
        return Response({"reserva_id": appointment.id, "status": appointment.status})
