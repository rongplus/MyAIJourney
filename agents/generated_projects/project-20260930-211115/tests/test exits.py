<<<<<<< SEARCH
=======
import pytest
from django.urls import reverse
from .views import exit_user_view

@pytest.fixture
def client():
    return DjangoClient()

@pytest.mark.django_db
def test_exit_user(client):
    user = User.objects.create_user(username='testuser')
    response = client.post(reverse('exit'), {'username': 'testuser'})
    assert response.status_code == status.HTTP_200_OK
    assert 'exit_success.html' in str(response.rendered_content)

@pytest.mark.django_db
def test_exit_unauthorized(client):
    user = User.objects.create_user(username='testuser')
    response = client.post(reverse('exit'), {'username': 'nonexistent'})
    assert response.status_code == status.HTTP_403_FORBIDDEN
>>>>>>> REPLACE
