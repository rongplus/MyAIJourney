<<<<<<< SEARCH
=======
import pytest
from django.urls import reverse
from .views import registration_view, login_view, chat_view, send_message_view, search_view

@pytest.fixture
def client():
    return DjangoClient()

@pytest.mark.django_db
def test_message_count(client):
    messages = Message.objects.create_batch(size=10)
    assert len(messages) == 10

@pytest.mark.django_db
def test_message_search(client):
    messages = Message.objects.create_batch(size=10, message='test message')
    response = client.get(reverse('search'), {'query': 'test'})
    assert response.status_code == status.HTTP_200_OK
    assert 'search_results.html' in str(response.rendered_content)
>>>>>>> REPLACE
