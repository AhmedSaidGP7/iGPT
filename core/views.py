from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from datetime import datetime
from django.contrib.auth.decorators import login_required
from .models import *

# Create your views here.
@login_required
def index(request):
    return render(request, 'core/index.html')