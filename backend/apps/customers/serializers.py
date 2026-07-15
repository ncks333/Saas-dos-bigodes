from rest_framework import serializers

from core.utils.phones import (
    brazilian_whatsapp_lookup_values,
    normalize_brazilian_whatsapp,
)

from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "name", "whatsapp", "notes", "active", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]

    def validate_whatsapp(self, value):
        try:
            normalized = normalize_brazilian_whatsapp(value)
        except ValueError as exc:
            raise serializers.ValidationError("WhatsApp inválido.") from exc
        request = self.context.get("request")
        tenant_id = getattr(getattr(request, "user", None), "barbershop_id", None)
        existing = Customer.objects.filter(
            barbershop_id=tenant_id,
            whatsapp__in=brazilian_whatsapp_lookup_values(normalized),
        )
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError("WhatsApp já cadastrado nesta barbearia.")
        return normalized
