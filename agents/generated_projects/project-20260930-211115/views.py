# -*- coding: utf-8 -*-
from django.views import generic
from django.views.decorators.http import require_http_methods
from .models import User, Message, SearchResult

@require_http_methods(["POST"])
def registration_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        if User.objects.create_user(username, password):
            return render(request, 'success.html')
    return render(request, 'registration.html')

@require_http_methods(["POST"])
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = User.objects.filter(username=username).first()
        if user and user.check_password(password):
            user.set_password(password)
            user.save()
            return render(request, 'login_success.html')
    return render(request, 'login.html')

@require_http_methods(["POST"])
def chat_view(request):
    if request.method == 'POST':
        message = request.POST.get('message')
        if message:
            Message.objects.create(user=request.user, message=message, timestamp=datetime.datetime.now())
            return render(request, 'chat.html')
    return render(request, 'chat.html')

@require_http_methods(["GET"])
def search_view(request):
    if request.method == 'GET':
        query = request.GET.get('query')
        if query:
            messages = Message.objects.filter(
                Q(user__username__icontains=query) | 
                Q(message__icontains=query)
            ).order_by('-timestamp')
            SearchResult.objects.create(query=query, messages=messages)
            return render(request, 'search_results.html', {'search_results': SearchResult.objects.get_queryset().filter(query=query)})
    return render(request, 'search.html')

@require_http_methods(["POST"])
def send_message_view(request):
    if request.method == 'POST':
        user = request.user
        message = request.POST.get('message')
        if message:
            Message.objects.create(user=user, message=message, timestamp=datetime.datetime.now())
            return render(request, 'chat.html')
    return render(request, 'chat.html')

@require_http_methods(["POST"])
def exit_user_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        if User.objects.filter(username=username).first():
            user = User.objects.filter(username=username).first()
            user.is_admin = not user.is_admin
            user.save()
            return render(request, 'exit_success.html')
    return render(request, 'exit.html')
