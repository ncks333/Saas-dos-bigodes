from dataclasses import dataclass
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.utils import timezone


class AsaasCheckoutError(RuntimeError):
    pass


class AsaasCheckoutNotCreatedError(AsaasCheckoutError):
    """Asaas rejected request before a checkout could be created."""


class AsaasCheckoutOutcomeUnknownError(AsaasCheckoutError):
    """Asaas may have created checkout, but caller cannot verify outcome."""

    def __init__(self, message, *, checkout_id=""):
        super().__init__(message)
        self.checkout_id = checkout_id


@dataclass(frozen=True)
class CheckoutResult:
    id: str
    url: str


@dataclass(frozen=True)
class PaidCheckoutReconciliation:
    checkout_id: str
    external_reference: str
    provider_subscription_id: str = ""


def validate_checkout_url(url: str) -> str:
    if not isinstance(url, str) or not url:
        raise AsaasCheckoutOutcomeUnknownError(
            "URL de checkout Asaas ausente ou inválida"
        )
    try:
        parsed = urlsplit(url)
    except ValueError:
        raise AsaasCheckoutOutcomeUnknownError(
            "URL de checkout Asaas ausente ou inválida"
        ) from None
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or origin not in settings.ASAAS_CHECKOUT_ALLOWED_ORIGINS
    ):
        raise AsaasCheckoutOutcomeUnknownError(
            "URL de checkout Asaas fora das origens permitidas"
        )
    return url


def _create_checkout(
    subscription, user, next_due_date, *, external_reference=None
) -> CheckoutResult:
    payload = {
        "billingTypes": ["CREDIT_CARD"],
        "chargeTypes": ["RECURRENT"],
        "minutesToExpire": settings.ASAAS_CHECKOUT_EXPIRES_MINUTES,
        "externalReference": str(external_reference or subscription.external_reference),
        "callback": {
            "successUrl": f"{settings.FRONTEND_URL.rstrip('/')}/checkout/concluido",
            "cancelUrl": f"{settings.FRONTEND_URL.rstrip('/')}/checkout/cancelado",
            "expiredUrl": f"{settings.FRONTEND_URL.rstrip('/')}/checkout/expirado",
        },
        "items": [
            {
                "name": subscription.plan.name,
                "description": "Assinatura mensal M&R BarberHub",
                "quantity": 1,
                "value": float(subscription.plan.amount),
            }
        ],
        "subscription": {
            "cycle": "MONTHLY",
            "nextDueDate": next_due_date.date().isoformat(),
        },
    }
    try:
        response = requests.post(
            f"{settings.ASAAS_API_URL.rstrip('/')}/checkouts",
            json=payload,
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "access_token": settings.ASAAS_API_KEY,
            },
            timeout=10,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        status_code = getattr(exc.response, "status_code", None)
        if status_code == 400:
            raise AsaasCheckoutNotCreatedError(
                "Checkout Asaas recusado antes da criação"
            ) from None
        raise AsaasCheckoutOutcomeUnknownError(
            "Resultado da criação de checkout Asaas é desconhecido"
        ) from None
    except requests.RequestException:
        raise AsaasCheckoutOutcomeUnknownError(
            "Resultado da criação de checkout Asaas é desconhecido"
        ) from None

    try:
        data = response.json()
    except (TypeError, ValueError):
        raise AsaasCheckoutOutcomeUnknownError(
            "Resultado da criação de checkout Asaas é desconhecido"
        ) from None
    if not isinstance(data, dict):
        raise AsaasCheckoutOutcomeUnknownError(
            "Resultado da criação de checkout Asaas é desconhecido"
        )
    checkout_id = data.get("id")
    if not isinstance(checkout_id, str) or not checkout_id.strip():
        raise AsaasCheckoutOutcomeUnknownError(
            "Resultado da criação de checkout Asaas é desconhecido"
        )
    link = data.get("link")
    if link is not None and not isinstance(link, str):
        raise AsaasCheckoutOutcomeUnknownError(
            "Resultado da criação de checkout Asaas é desconhecido",
            checkout_id=checkout_id,
        )
    try:
        url = validate_checkout_url(
            link or f"{settings.ASAAS_CHECKOUT_BASE_URL}?id={checkout_id}"
        )
    except AsaasCheckoutOutcomeUnknownError as exc:
        raise AsaasCheckoutOutcomeUnknownError(
            str(exc), checkout_id=checkout_id
        ) from None
    return CheckoutResult(id=checkout_id, url=url)


def create_recurring_checkout(subscription, user) -> CheckoutResult:
    return _create_checkout(subscription, user, subscription.next_billing_at)


def create_regularization_checkout(subscription, user) -> CheckoutResult:
    return _create_checkout(
        subscription,
        user,
        timezone.now(),
        external_reference=(
            subscription.regularization_checkout_reference
            or subscription.external_reference
        ),
    )


def cancel_checkout(checkout_id: str) -> None:
    try:
        response = requests.post(
            f"{settings.ASAAS_API_URL.rstrip('/')}/checkouts/{checkout_id}/cancel",
            headers={
                "accept": "application/json",
                "access_token": settings.ASAAS_API_KEY,
            },
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException:
        raise AsaasCheckoutError("Falha ao cancelar checkout Asaas") from None


def reconcile_paid_checkout(
    checkout_id: str,
    expected_external_reference: str,
) -> PaidCheckoutReconciliation:
    if (
        not isinstance(checkout_id, str)
        or not checkout_id
        or len(checkout_id) > 100
        or "/" in checkout_id
    ):
        raise AsaasCheckoutError("ID de checkout Asaas inválido")
    if (
        not isinstance(expected_external_reference, str)
        or not expected_external_reference
        or len(expected_external_reference) > 200
    ):
        raise AsaasCheckoutError("Referência de checkout Asaas inválida")

    return PaidCheckoutReconciliation(
        checkout_id=checkout_id,
        external_reference=expected_external_reference,
    )


def _get_provider_json(url, *, headers, params=None):
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=10,
            params=params,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, TypeError, ValueError):
        raise AsaasCheckoutError("Falha ao reconciliar checkout Asaas") from None
    if not isinstance(data, dict):
        raise AsaasCheckoutError("Resposta de reconciliação Asaas inválida")
    return data
