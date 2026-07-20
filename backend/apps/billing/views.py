from rest_framework import serializers, status
from rest_framework.exceptions import APIException, NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_event
from core.security.turnstile import verify_turnstile

from .models import SubscriptionPlan
from .providers.asaas import AsaasCheckoutError
from .serializers import PublicPlanSerializer, SignupSerializer
from .services import provision_signup


class ProviderUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Checkout indisponível. Tente novamente."
    default_code = "provider_unavailable"


class PublicPlanView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        plan = SubscriptionPlan.objects.filter(active=True).order_by("id").first()
        if plan is None:
            raise NotFound("Plano indisponível.")
        return Response(PublicPlanSerializer(plan).data)


class SignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not verify_turnstile(
            serializer.validated_data["captcha_token"],
            request.META.get("REMOTE_ADDR"),
        ):
            raise serializers.ValidationError("Verificação anti-bot inválida.")
        plan = SubscriptionPlan.objects.filter(
            code=serializer.validated_data["plan_code"],
            active=True,
        ).first()
        if plan is None:
            raise serializers.ValidationError({"plan_code": "Plano indisponível."})
        try:
            subscription, checkout = provision_signup(serializer.validated_data, plan)
        except AsaasCheckoutError as exc:
            raise ProviderUnavailable() from exc
        user = subscription.barbershop.users.get(role="ADMIN")
        record_event(
            user, "BILLING_SIGNUP_CREATED", target=subscription, request=request
        )
        return Response(
            {
                "checkout_url": checkout.url,
                "external_reference": str(subscription.external_reference),
            },
            status=status.HTTP_201_CREATED,
        )
