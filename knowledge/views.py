from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from datetime import datetime
from django.contrib.auth.decorators import login_required
from .models import *
from .forms import KnowledgeBaseForm
from core.models import OpenAISettings

# Create your views here
@login_required
def faq(request, agent_id: int):
    try:
        agent = get_object_or_404(OpenAISettings, pk=agent_id)
    except ObjectDoesNotExist:
         return render(request, '404_template.html', {'message': f'Agent ID {agent_id} not found.'}, status=404)
        
    knowledgebase = KnowledgeBase.objects.filter(agent=agent).select_related('agent')
    return render(request, 'knowledge/faq.html',{
        'knowledgebase' : knowledgebase,
        'current_agent': agent,
    })


@login_required
def add_question(request, agent_id: int):
    # 💥 الخطوة 1: جلب كائن الوكيل
    agent = get_object_or_404(OpenAISettings, pk=agent_id)

    if request.method == 'POST':
        form = KnowledgeBaseForm(request.POST)
        if form.is_valid():
            kb = form.save(commit=False)
            kb.agent = agent
            kb.save()
            return redirect('knowledge:faq', agent_id=agent_id) 
    else:
        form = KnowledgeBaseForm()
        
    return render(request, 'knowledge/add_question.html', {
        'form': form, 
        'current_agent': agent 
    })


@login_required
def edit_question(request, agent_id: int, pk: int):
    agent = get_object_or_404(OpenAISettings, pk=agent_id)
    
    kb = get_object_or_404(KnowledgeBase, pk=pk, agent=agent) 

    if request.method == 'POST':
        form = KnowledgeBaseForm(request.POST, instance=kb)
        if form.is_valid():
            form.save()
            return redirect('knowledge:faq', agent_id=agent_id) 
    else:
        form = KnowledgeBaseForm(instance=kb)

    return render(request, 'knowledge/edit_question.html', {
        'form': form, 
        'kb': kb,
        'current_agent': agent
    })