import hmac
from collections.abc import Mapping

from django.conf import settings
from rest_framework import serializers, status
from rest_framework.exceptions import APIException, NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.security.turnstile import verify_turnstile

from .models import BillingWebhookEvent, Subscription, SubscriptionPlan
from .providers.asaas import AsaasCheckoutError
from .serializers import PublicPlanSerializer, SignupSerializer
from .services import provision_signup, sanitize_asaas_webhook_payload
from .tasks import process_billing_webhook


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
            subscription, checkout = provision_signup(
                serializer.validated_data,
                plan,
                request=request,
            )
        except AsaasCheckoutError as exc:
            raise ProviderUnavailable() from exc
        return Response(
            {
                "checkout_url": checkout.url,
                "external_reference": str(subscription.external_reference),
            },
            status=status.HTTP_201_CREATED,
        )


class AsaasWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        received_token = request.headers.get("asaas-access-token", "")
        expected_token = settings.ASAAS_WEBHOOK_TOKEN
        token_matches = hmac.compare_digest(received_token, expected_token)
        if not expected_token or not token_matches:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        payload = request.data
        if not isinstance(payload, Mapping):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        provider_event_id = payload.get("id")
        event_type = payload.get("event")
        if (
            not isinstance(provider_event_id, str)
            or not provider_event_id
            or len(provider_event_id) > 150
            or not isinstance(event_type, str)
            or not event_type
            or len(event_type) > 100
        ):
            return Response(status=status.HTTP_400_BAD_REQUEST)

        event, created = BillingWebhookEvent.objects.get_or_create(
            provider=Subscription.Provider.ASAAS,
            provider_event_id=provider_event_id,
            defaults={
                "event_type": event_type,
                "payload": sanitize_asaas_webhook_payload(payload),
            },
        )
        if created:
            process_billing_webhook.delay(event.id)
        return Response({"accepted": True}, status=status.HTTP_202_ACCEPTED)
