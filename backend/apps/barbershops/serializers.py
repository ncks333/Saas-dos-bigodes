from rest_framework import serializers
from .models import Barbershop, OperatingHour


class OperatingHourSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperatingHour
        fields = ["id", "weekday", "opens_at", "closes_at", "active"]

    def validate(self, attrs):
        if attrs["closes_at"] <= attrs["opens_at"]:
            raise serializers.ValidationError("O fechamento deve ser posterior à abertura.")
        return attrs


class BarbershopSerializer(serializers.ModelSerializer):
    operating_hours = OperatingHourSerializer(many=True, read_only=True)

    class Meta:
        model = Barbershop
        fields = ["id", "name", "slug", "whatsapp", "timezone", "active", "operating_hours"]
        read_only_fields = ["slug"]
