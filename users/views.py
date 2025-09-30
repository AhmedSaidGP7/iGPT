from django.shortcuts import render
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.shortcuts import render
from django.http import HttpResponse
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from datetime import datetime
from django.contrib.auth.decorators import login_required

# Create your views here.

# The view that handles authentication
def auth(request):
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse("core:index"))
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if 'next'in request.POST:
                return HttpResponseRedirect(request.POST.get('next'))
            else:    
                return HttpResponseRedirect(reverse("core:index"))
        else:
            return render(request, "users/login.html", {
                "message": "برجاء التأكد من اسم المستخدم وكلمة المرور "
            })
    else:
        return render(request, "users/login.html")

# The view that handles singing out 
def signout(request):
    logout(request)
    return render(request, "users/login.html")
