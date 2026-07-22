from django.core.management.base import BaseCommand, CommandError

from apps.billing.models import Subscription
from apps.billing.services import reconcile_regularization_checkout


class Command(BaseCommand):
    help = "Reconcilia checkout de regularização após confirmação manual no Asaas"

    def add_arguments(self, parser):
        parser.add_argument("--subscription-id", type=int, required=True)
        parser.add_argument("--verified-checkout-id")
        parser.add_argument("--verified-checkout-url")
        parser.add_argument("--attempt-reference")
        parser.add_argument(
            "--reset-confirmed-no-active-checkout",
            action="store_true",
        )

    def handle(self, *args, **options):
        try:
            subscription = reconcile_regularization_checkout(
                options["subscription_id"],
                checkout_id=options["verified_checkout_id"] or "",
                checkout_url=options["verified_checkout_url"] or "",
                attempt_reference=options["attempt_reference"],
                reset_confirmed_no_active_checkout=options[
                    "reset_confirmed_no_active_checkout"
                ],
            )
        except (ValueError, Subscription.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Reconciliação concluída para assinatura {subscription.id}."
            )
        )
