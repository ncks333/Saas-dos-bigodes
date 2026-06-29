import re
from rest_framework import serializers
from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "name", "whatsapp", "notes", "active", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]

    def validate_whatsapp(self, value):
        digits = re.sub(r"\D", "", value)
        if not 10 <= len(digits) <= 15:
            raise serializers.ValidationError("WhatsApp inválido.")
        request = self.context.get("request")
        tenant_id = getattr(getattr(request, "user", None), "barbershop_id", None)
        existing = Customer.objects.filter(barbershop_id=tenant_id, whatsapp=digits)
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError("WhatsApp já cadastrado nesta barbearia.")
        return digits
