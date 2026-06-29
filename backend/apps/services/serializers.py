from rest_framework import serializers
from .models import Service


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ["id", "name", "description", "price", "duration_minutes", "active", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]

    def validate_name(self, value):
        request = self.context.get("request")
        tenant_id = getattr(getattr(request, "user", None), "barbershop_id", None)
        existing = Service.objects.filter(barbershop_id=tenant_id, name__iexact=value.strip())
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if tenant_id and existing.exists():
            raise serializers.ValidationError("Serviço já cadastrado nesta barbearia.")
        return value.strip()
