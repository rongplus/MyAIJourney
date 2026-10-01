# -*- coding: utf-8 -*-
import os
from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from rest_framework.response import Response
from rest_framework import status
from .models import User, Message, SearchResult
from ..rabbitmq import send_to_queue, get_from_queue
from .views import registration_view, login_view, chat_view, search_view, send_message_view, exit_user_view

def index(request):
    return render(request, 'chat.html')

@csrf_exempt
def registration(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        if User.objects.create_user(username, password):
            return registration_view(request)
    return render(request, 'registration.html')

@csrf_exempt
def login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        if User.objects.filter(username=username).first():
            return login_view(request)
    return render(request, 'login.html')

@csrf_exempt
def chat(request):
    if request.method == 'POST':
        message = request.POST.get('message')
        if send_message_view(request):
            send_to_queue(message)
            return render(request, 'chat.html')
    return render(request, 'chat.html')

@csrf_exempt
def search(request):
    if request.method == 'POST':
        query = request.POST.get('query')
        results = SearchResult.objects.filter(Q(username__icontains=query) | Q(message__icontains=query))
        return search_view(request, results)
    return render(request, 'search.html')

@csrf_exempt
def exit_user(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        if User.objects.filter(username=username).first():
            exit_user_view(request)
    return render(request, 'exit.html')

# 其他中间件和视图函数
