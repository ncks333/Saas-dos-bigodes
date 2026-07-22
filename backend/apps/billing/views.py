import hmac
import logging
from collections.abc import Mapping

from django.conf import settings
from django.core.signing import BadSignature
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework import serializers, status
from rest_framework.exceptions import APIException, NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.security.turnstile import verify_turnstile

from .models import BillingWebhookEvent, Subscription, SubscriptionPlan
from .providers.asaas import AsaasCheckoutError, validate_checkout_url
from .serializers import (
    PublicPlanSerializer,
    RegularizationCheckoutSerializer,
    RegularizationRequestSerializer,
    SignupSerializer,
)
from .services import (
    provision_regularization_checkout,
    provision_signup,
    persist_regularization_email_request,
    regularization_subscription_from_token,
    sanitize_asaas_webhook_payload,
)
from .tasks import (
    prepare_billing_webhook_dispatch,
    process_billing_webhook,
    release_billing_webhook_dispatch,
    send_regularization_request_email,
)
from .throttles import RegularizationCheckoutThrottle, RegularizationRequestThrottle


logger = logging.getLogger(__name__)


class ProviderUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Checkout indisponível. Tente novamente."
    default_code = "provider_unavailable"


class PublicPlanView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        plan = _public_plan()
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
        plan = _public_plan()
        if plan is None:
            raise serializers.ValidationError({"plan": "Plano indisponível."})
        try:
            subscription, checkout = provision_signup(
                serializer.validated_data,
                plan,
                request=request,
            )
        except AsaasCheckoutError as exc:
            raise ProviderUnavailable() from exc
        try:
            validate_checkout_url(checkout.url)
        except AsaasCheckoutError as exc:
            raise ProviderUnavailable() from exc
        return Response(
            {
                "checkout_url": checkout.url,
                "external_reference": str(subscription.external_reference),
            },
            status=status.HTTP_201_CREATED,
        )


@method_decorator(ratelimit(key="ip", rate="5/h", method="POST", block=True), name="dispatch")
class RegularizationRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [RegularizationRequestThrottle]

    def post(self, request):
        serializer = RegularizationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email_request = persist_regularization_email_request(
            serializer.validated_data["email"]
        )
        if email_request is not None:
            try:
                send_regularization_request_email.delay(email_request.id)
            except Exception:
                pass
        return Response(
            {
                "message": (
                    "Se a conta precisar de regularização, enviaremos as instruções."
                )
            }
        )


@method_decorator(ratelimit(key="ip", rate="5/h", method="POST", block=True), name="dispatch")
class RegularizationCheckoutView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [RegularizationCheckoutThrottle]

    def post(self, request):
        serializer = RegularizationCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            subscription = regularization_subscription_from_token(
                serializer.validated_data["token"]
            )
        except BadSignature:
            raise serializers.ValidationError(
                {"token": "Token inválido ou expirado."}
            ) from None
        if subscription is None or subscription.allows_access:
            raise serializers.ValidationError(
                {"token": "Token inválido ou expirado."}
            )
        try:
            checkout = provision_regularization_checkout(subscription)
        except AsaasCheckoutError as exc:
            raise ProviderUnavailable() from exc
        except ValueError:
            raise serializers.ValidationError(
                {"token": "Token inválido ou expirado."}
            ) from None
        if checkout is None:
            raise serializers.ValidationError(
                {"token": "Token inválido ou expirado."}
            )
        try:
            validate_checkout_url(checkout.url)
        except AsaasCheckoutError as exc:
            raise ProviderUnavailable() from exc
        return Response({"checkout_url": checkout.url})


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
                if prepare_billing_webhook_dispatch(event.id):
                    process_billing_webhook.delay(event.id)
            except Exception:
                logger.exception(
                    "Webhook Asaas persistido, mas despacho imediato falhou",
                    extra={"billing_webhook_event_id": event.id},
                )
                try:
                    release_billing_webhook_dispatch(event.id)
                except Exception:
                    logger.exception(
                        "Falha ao liberar lease de webhook Asaas persistido",
                        extra={"billing_webhook_event_id": event.id},
                    )
        return Response({"accepted": True}, status=status.HTTP_200_OK)


def _valid_provider_identifier(value, max_length):
    return (
        isinstance(value, str)
        and 0 < len(value) <= max_length
        and all(character.isprintable() and not character.isspace() for character in value)
    )


def _public_plan():
    return SubscriptionPlan.objects.filter(
        active=True,
        code=settings.BILLING_PUBLIC_PLAN_CODE,
    ).first()
