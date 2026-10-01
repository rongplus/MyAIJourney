<<<<<<< SEARCH
=======
import pytest
from django.urls import reverse
from .views import registration_view, login_view, chat_view, send_message_view, exit_user_view

@pytest.fixture
def client():
    return DjangoClient()

@pytest.mark.django_db
def test_registration限制(client):
    response = client.post(reverse('register'), {
        'username': 'testuser' * 200,
        'password': 'testpass123'
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'handle registration error' in str(response.rendered_content)

@pytest.mark.django_db
def test_login限制(client):
    response = client.post(reverse('login'), {
        'username': 'testuser' * 200,
        'password': 'testpass123'
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'handle registration error' in str(response.rendered_content)
>>>>>>> REPLACE
