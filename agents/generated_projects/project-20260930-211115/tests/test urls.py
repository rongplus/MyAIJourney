<<<<<<< SEARCH
=======
import pytest
from django.urls import reverse
from .urls import *
from .views import registration_view, login_view, chat_view, search_view, send_message_view, exit_user_view

@pytest.mark.django_db
def test_chat_url(client):
    response = client.post(reverse('chat'), {
        'message': 'Hello world'
    })
    assert response.status_code == status.HTTP_200_OK
    assert 'chat.html' in str(response.rendered_content)

@pytest.mark.django_db
def test_search_url(client):
    response = client.get(reverse('search'))
    assert response.status_code == status.HTTP_200_OK
    assert 'search_results.html' in str(response.rendered_content)

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

@pytest.mark.django_db
def test_exit_url(client):
    user = User.objects.create_user(username='testuser')
    response = client.post(reverse('exit'), {'username': 'testuser'})
    assert response.status_code == status.HTTP_200_OK
    assert 'exit_success.html' in str(response.rendered_content)
>>>>>>> REPLACE
