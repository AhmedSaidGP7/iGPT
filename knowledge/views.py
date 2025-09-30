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

@login_required
def edit_question(request, pk):
    kb = get_object_or_404(KnowledgeBase, pk=pk)

    if request.method == 'POST':
        form = KnowledgeBaseForm(request.POST, instance=kb)
        if form.is_valid():
            kb = form.save(commit=False)
            # إعادة توليد الـ embedding بعد تعديل السؤال
            kb.embedding = get_embeddings(kb.question)
            kb.save()
            return redirect('knowledge:faq')  # عدل الرابط حسب مكان قائمة الأسئلة
    else:
        form = KnowledgeBaseForm(instance=kb)

    return render(request, 'knowledge/edit_question.html', {'form': form, 'kb': kb})