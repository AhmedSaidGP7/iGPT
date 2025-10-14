from django.urls import path
from . import views

app_name = "core"
urlpatterns = [
    path("", views.index, name="index"),
    path('agents/<int:agent_id>/view/', views.view_agent, name='view_agent'),
    path('agents/add/', views.add_agent, name='add_agent'),
    path('agents/<int:agent_id>/edit/', views.edit_agent, name='edit_agent'),
   
]