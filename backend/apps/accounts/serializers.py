from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenObtainSerializer,
)
from rest_framework_simplejwt.settings import api_settings

from apps.billing.access import user_has_subscription_access

from .models import User


class LoginSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["barbershop_id"] = user.barbershop_id
        return token

    def validate(self, attrs):
        data = TokenObtainSerializer.validate(self, attrs)
        if not self.user.barbershop_id:
            raise serializers.ValidationError("Usuário sem barbearia associada.")
        if not user_has_subscription_access(self.user):
            raise PermissionDenied(
                {
                    "code": "subscription_required",
                    "detail": "Assinatura precisa ser regularizada.",
                }
            )
        refresh = self.get_token(self.user)
        data["refresh"] = str(refresh)
        data["access"] = str(refresh.access_token)
        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, self.user)
        data["user"] = {"id": self.user.id, "name": self.user.get_full_name(), "role": self.user.role}
        return data


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Senha atual incorreta.")
        return value

    def validate_new_password(self, value):
        validate_password(value, self.context["request"].user)
        return value

    def save(self):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "role", "password", "is_active"]

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            message = "Campo obrigatório."
            raise serializers.ValidationError({"password": message})
        return User.objects.create_user(password=password, **validated_data)
