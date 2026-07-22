from datetime import timedelta

import pytest
from django.utils import timezone

from apps.billing.models import Subscription


@pytest.mark.django_db
def test_dashboard_returns_current_tenant_trial_end(api_client, subscription):
    subscription.status = Subscription.Status.TRIAL
    subscription.trial_ends_at = timezone.now() + timedelta(days=29)
    subscription.save(update_fields=["status", "trial_ends_at", "updated_at"])

    response = api_client.get("/api/v1/dashboard/")

    assert response.status_code == 200
    assert response.data["subscription_status"] == "TRIAL"
    assert response.data["trial_ends_at"] == subscription.trial_ends_at
