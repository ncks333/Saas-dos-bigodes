from rest_framework import serializers
from .models import Appointment, ScheduleBlock


class AppointmentSerializer(serializers.ModelSerializer):
    cancellation_token = serializers.SerializerMethodField()
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)

    class Meta:
        model = Appointment
        fields = ["id", "customer", "customer_name", "service", "service_name", "employee", "starts_at", "ends_at", "duration_minutes", "notes", "status", "source", "cancellation_token", "created_at"]
        read_only_fields = ["ends_at", "duration_minutes", "source", "cancellation_token", "created_at"]

    def validate(self, attrs):
        request = self.context.get("request")
        tenant_id = getattr(getattr(request, "user", None), "barbershop_id", None)
        for field in ("customer", "service", "employee"):
            value = attrs.get(field)
            if value is not None and value.barbershop_id != tenant_id:
                raise serializers.ValidationError({field: "Registro inválido para esta barbearia."})
        return attrs

    def get_cancellation_token(self, obj):
        return self.context.get("cancellation_token")


class ScheduleBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduleBlock
        fields = ["id", "starts_at", "ends_at", "reason", "created_at"]

    def validate(self, attrs):
        if attrs["ends_at"] <= attrs["starts_at"]:
            raise serializers.ValidationError("O término deve ser posterior ao início.")
        return attrs
