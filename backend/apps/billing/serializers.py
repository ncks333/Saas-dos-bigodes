from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from apps.accounts.models import User
from apps.barbershops.models import Barbershop
from core.utils.phones import normalize_brazilian_whatsapp

from .models import SubscriptionPlan


class PublicPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ["code", "name", "amount", "currency", "trial_days"]


class SignupSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    email = serializers.EmailField(
        validators=[UniqueValidator(queryset=User.objects.all())]
    )
    username = serializers.CharField(
        max_length=150, validators=[UniqueValidator(queryset=User.objects.all())]
    )
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    barbershop_name = serializers.CharField(max_length=150)
    slug = serializers.SlugField(
        max_length=80, validators=[UniqueValidator(queryset=Barbershop.objects.all())]
    )
    whatsapp = serializers.CharField(max_length=20)
    plan_code = serializers.SlugField(max_length=50)
    captcha_token = serializers.CharField(write_only=True)
    terms_accepted = serializers.BooleanField()

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_whatsapp(self, value):
        try:
            return normalize_brazilian_whatsapp(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_terms_accepted(self, value):
        if not value:
            raise serializers.ValidationError("Aceite dos termos é obrigatório.")
        return value
