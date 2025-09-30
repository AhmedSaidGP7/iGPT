from django.urls import path
from . import views

app_name = "knowledge"
urlpatterns = [
    path("faq/", views.faq, name="faq"),
    path('add/', views.add_question, name='add_knowledge'),
    path('faq/edit/<int:pk>/', views.edit_question, name='edit_question'),
   
]