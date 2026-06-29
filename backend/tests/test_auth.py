import pytest


@pytest.mark.django_db
def test_login_returns_tenant_claim(client, user, barbershop):
    response = client.post("/api/v1/auth/login/", {"username": "admin", "password": "Senha123"})
    assert response.status_code == 200
    assert response.json()["access"]


@pytest.mark.django_db
def test_weak_password_is_rejected(api_client):
    response = api_client.post("/api/v1/users/", {"username": "employee", "email": "e@example.com", "password": "fraca", "role": "FUNCIONARIO"})
    assert response.status_code == 400
