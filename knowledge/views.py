from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from datetime import datetime
from django.contrib.auth.decorators import login_required
from .models import *
from .forms import KnowledgeBaseForm

# Create your views here.
@login_required
def faq(request):
    knowledgebase = KnowledgeBase.objects.all()
    return render(request, 'knowledge/faq.html',{
        'knowledgebase' : knowledgebase,
    })

@login_required
def add_question(request):
    if request.method == 'POST':
        form = KnowledgeBaseForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('knowledge:faq')  # replace with your success url
    else:
        form = KnowledgeBaseForm()
    return render(request, 'knowledge/add_question.html', {'form': form})
