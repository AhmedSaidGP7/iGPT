from django.urls import path
from . import views

app_name = "knowledge"
urlpatterns = [
    path('<int:agent_id>/add/', views.add_question, name='add_knowledge_to_agent'),
    path('<int:agent_id>/faq/', views.faq, name="faq"), 
    path('<int:agent_id>/faq/edit/<int:pk>/', views.edit_question, name='edit_question'),
   
]