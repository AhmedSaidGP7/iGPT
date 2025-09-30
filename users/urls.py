from django.urls import path
from . import views

app_name = "users"
urlpatterns = [
    path("auth", views.auth, name="login"),
    path("signout", views.signout, name="signout")
]