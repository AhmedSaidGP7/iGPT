from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from datetime import datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import *
from .forms import OpenAISettingsForm

# Create your views here.
@login_required
def index(request):
    agents = OpenAISettings.objects.all().order_by('agent_name')
    return render(request, 'core/index.html')

@login_required
def view_agent(request, agent_id):
    agent = get_object_or_404(OpenAISettings, id=agent_id)
    # Generate Webhook URL dynamically
    webhook_url = request.build_absolute_uri(reverse('webhook:agent_webhook', args=[agent.id]))
    return render(request, 'core/view_agent.html', {
     'agent': agent,
     'webhook_url': webhook_url
     })

@login_required
def add_agent(request):
    if request.method == 'POST':
        form = OpenAISettingsForm(request.POST)
        if form.is_valid():
            agent = form.save()
            messages.success(request, f" تم إنشاء الوكيل {agent.agent_name} بنجاح.")
            return redirect('core:view_agent', agent_id=agent.id)
    else:
        form = OpenAISettingsForm()

    return render(request, 'core/add_agent.html', {'form': form})



@login_required
def edit_agent(request, agent_id):
    agent = get_object_or_404(OpenAISettings, id=agent_id)

    if request.method == 'POST':
        form = OpenAISettingsForm(request.POST, instance=agent)
        if form.is_valid():
            form.save()
            messages.success(request, f"تم تعديل الوكيل {agent.agent_name} بنجاح.")
            return redirect('core:view_agent', agent_id=agent.id)
    else:
        form = OpenAISettingsForm(instance=agent)

    return render(request, 'core/edit_agent.html', {'form': form, 'agent': agent})