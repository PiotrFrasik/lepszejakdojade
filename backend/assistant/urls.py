from django.urls import path

from .views import ChatView

app_name = "assistant"

urlpatterns = [
    path("assistant/chat/", ChatView.as_view(), name="chat"),
]
