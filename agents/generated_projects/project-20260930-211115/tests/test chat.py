<<<<<<< SEARCH
=======
import pytest
from django.urls import reverse
from .views import registration_view, login_view, chat_view, send_message_view

@pytest.fixture
def client():
    return DjangoClient()

@pytest.mark.django_db
def test_send_message(client):
    response = client.post(reverse('chat'), {
        'message': 'Hello world'
    })
    assert response.status_code == status.HTTP_200_OK
    assert 'chat.html' in str(response.rendered_content)

@pytest.mark.django_db
def test_search(client):
    response = client.get(reverse('search'))
    assert response.status_code == status.HTTP_200_OK
    assert 'search_results.html' in str(response.rendered_content)
>>>>>>> REPLACE
