# -*- coding: utf-8 -*-
from django.urls import path
from .views import registration_view, login_view, chat_view, search_view, send_message_view, exit_user_view

urlpatterns = [
    path('register/', registration_view, name='registration'),
    path('login/', login_view, name='login'),
    path('chat/', chat_view, name='chat'),
    path('search/', search_view, name='search'),
    path('message/', send_message_view, name='message'),
    path('exit/', exit_user_view, name='exit'),
]
