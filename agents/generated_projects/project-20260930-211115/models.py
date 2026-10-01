# -*- coding: utf-8 -*-
from django.db import models
from django.core.validators import MaxLengthValidator

class User(models.Model):
    username = models.CharField(max_length=200, unique=True, verbose_name='用户名')
    password = models.CharField(max_length=200, verbose_name='密码')
    email = models.CharField(max_length=200, verbose_name='邮箱')
    is_admin = models.BooleanField(default=False, verbose_name='是否管理员')
    date_joined = models.DateTimeField(auto_now_add=True, verbose_name='注册时间')

    def __str__(self):
        return self.username

class Message(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='发送者')
    message = models.TextField(max_length=2000, verbose_name='消息')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='发送时间')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='接收者')

    def __str__(self):
        return f"{self.user.username}:{self.message[:50]}..."

class SearchResult(models.Model):
    query = models.CharField(max_length=200, verbose_name='搜索词')
    messages = models.ManyToManyField(Message, verbose_name='搜索结果')

    def __str__(self):
        return f"{self.query}"
