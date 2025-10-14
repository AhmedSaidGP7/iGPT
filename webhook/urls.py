from django.urls import path
from . import views

app_name = "webhook"
urlpatterns = [
    path('<int:agent_id>/', views.webhook, name='agent_webhook'),
    #path("", views.webhook, name="index"),
   
]