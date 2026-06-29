import pytest
from apps.customers.models import Customer


@pytest.mark.django_db
def test_customer_list_is_isolated(api_client, barbershop, other_barbershop):
    Customer.objects.create(barbershop=barbershop, name="Meu cliente", whatsapp="5511999999999")
    Customer.objects.create(barbershop=other_barbershop, name="Cliente alheio", whatsapp="5511888888888")
    response = api_client.get("/api/v1/customers/")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["name"] == "Meu cliente"


@pytest.mark.django_db
def test_cannot_read_customer_from_another_tenant(api_client, other_barbershop):
    customer = Customer.objects.create(barbershop=other_barbershop, name="Cliente alheio", whatsapp="5511888888888")
    assert api_client.get(f"/api/v1/customers/{customer.id}/").status_code == 404
