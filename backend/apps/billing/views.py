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
from .tasks import (
    prepare_billing_webhook_dispatch,
    process_billing_webhook,
    release_billing_webhook_dispatch,
)


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
        token_matches = hmac.compare_digest(
            received_token.encode(), expected_token.encode()
        )
        if not expected_token or not token_matches:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        payload = request.data
        if not isinstance(payload, Mapping):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        provider_event_id = payload.get("id")
        event_type = payload.get("event")
        if (
            not _valid_provider_identifier(provider_event_id, 150)
            or not _valid_provider_identifier(event_type, 100)
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
        if created or event.processed_at is None:
            try:
                if prepare_billing_webhook_dispatch(event.id, force=True):
                    process_billing_webhook.delay(event.id)
            except Exception:
                release_billing_webhook_dispatch(event.id)
                return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"accepted": True}, status=status.HTTP_202_ACCEPTED)


def _valid_provider_identifier(value, max_length):
    return (
        isinstance(value, str)
        and 0 < len(value) <= max_length
        and all(character.isprintable() and not character.isspace() for character in value)
    )
