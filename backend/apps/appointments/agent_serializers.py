from rest_framework import serializers


class AvailabilityToolSerializer(serializers.Serializer):
    data = serializers.DateField()
    servico_id = serializers.IntegerField(min_value=1)


class UserReservationsToolSerializer(serializers.Serializer):
    usuario_id = serializers.IntegerField(min_value=1)
    data = serializers.DateField()


class CreateReservationToolSerializer(UserReservationsToolSerializer):
    servico_id = serializers.IntegerField(min_value=1)
    horario = serializers.TimeField()


class CancelReservationToolSerializer(serializers.Serializer):
    reserva_id = serializers.IntegerField(min_value=1)
    confirmacao_explicita = serializers.BooleanField()

    def validate_confirmacao_explicita(self, value):
        if value is not True:
            raise serializers.ValidationError(
                "O cancelamento exige confirmação explícita do usuário."
            )
        return value
