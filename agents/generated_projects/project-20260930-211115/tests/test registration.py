<<<<<<< SEARCH
=======
import pytest
from django.urls import reverse
from .views import registration_view, login_view

@pytest.fixture
def client():
    return DjangoClient()

@pytest.mark.django_db
def test_register(client):
    response = client.post(reverse('register'), {
        'username': 'testuser',
        'password': 'testpass123'
    })
    assert response.status_code == status.HTTP_201_CREATED
    assert 'success.html' in str(response.rendered_content)

@pytest.mark.django_db
def test_login(client):
    response = client.post(reverse('login'), {
        'username': 'testuser',
        'password': 'testpass123'
    })
    assert response.status_code == status.HTTP_200_OK
    assert 'login_success.html' in str(response.rendered_content)

@pytest.mark.django_db
def test_chat(client):
    response = client.post(reverse('chat'), {
        'message': 'Hello world'
    })
    assert response.status_code == status.HTTP_200_OK
    assert 'chat.html' in str(response.rendered_content)
>>>>>>> REPLACE
