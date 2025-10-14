import json
import logging
import requests
import threading
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from .models import Client, Message, Response
from core.models import OpenAISettings
from .rag_utilities import (
    get_embeddings,
    find_most_similar_question,
    generate_answer,
    transcribe_audio_from_base64,
)
from .utils import get_agent_settings_by_id
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from .rag_utilities import (
    get_embeddings,
    find_most_similar_question,
    generate_answer,
    transcribe_audio_from_base64,
)

logger = logging.getLogger(__name__)

# Debounce settings
DEBOUNCE_TIME = 2  # Waiting time in sec
_user_buffers = {} 



def send_message_to_client(jid: str, text: str, instance_id: str, evolution_key: str, server_url: str):

    try:
        url = f"{server_url}/message/sendText/{instance_id}"
        headers = {
            "apikey": evolution_key,
            "Content-Type": "application/json"
        }
        payload = {
            "number": jid.split('@')[0],
            "text": text,
            "delay": 0,
            "linkPreview": True,
        }
        
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        logger.info(f"Message sent successfully to {jid} (Instance {instance_id}).")
        return response.json()
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending message to {jid}: {e}")
        return None


def _process_buffered_message_logic(jid: str, instance_id: str, evolution_key: str, server_url: str, agent_settings: OpenAISettings):
  
    buffer_key = f"{jid}:{instance_id}"
    
    if buffer_key not in _user_buffers:
        return
        
    user_message_content = _user_buffers[buffer_key]['content']
    message_type = _user_buffers[buffer_key]['message_type']
    image_url = _user_buffers[buffer_key]['image_url']
    
    del _user_buffers[buffer_key] # تفريغ الـ buffer

    try:
        with transaction.atomic():
            # 1. إنشاء سجل الرسالة
            client, _ = Client.objects.get_or_create(jid=jid)
            user_message = Message.objects.create(
                client=client,
                message_type=message_type,
                content=user_message_content,
                image_url=image_url,
            )

            # 2. بناء سجل المحادثة (History)
            conversation_history = []
            # استخدام select_related لتحسين الأداء (تقليل استعلامات N+1)
            messages = Message.objects.filter(client=client).select_related('client', 'response').order_by('-timestamp')[:5]
            
            for msg in reversed(messages):
                if msg.content:
                    conversation_history.append({"role": "user", "content": msg.content})
                    
                    try:
                        # Access the related Response object directly
                        ai_response = msg.response
                        conversation_history.append({"role": "assistant", "content": ai_response.content})
                    except Response.DoesNotExist: 
                        # This exception is raised if the Message has no related Response object
                        pass

            # 3. استرجاع السياق من قاعدة المعرفة المخصصة للوكيل
            # استخدام related_name: agent.knowledge_chunks
            knowledge_base_chunks = list(agent_settings.knowledge_chunks.all())
            
            user_embedding = get_embeddings(user_message.content)
            similar_questions_info = find_most_similar_question(user_embedding, knowledge_base_chunks)
            context_questions = [item[1].question for item in similar_questions_info]
            
            # 4. توليد الرد
            reply_text = generate_answer(
                user_message.content,
                context_questions,
                conversation_history,
                agent_settings # تمرير الإعدادات الديناميكية
            )

            # 5. حفظ الرد
            Response.objects.create(message=user_message, content=reply_text)
        
        # 6. إرسال الرد (خارج الـ transaction)
        send_message_to_client(jid, reply_text, instance_id, evolution_key, server_url)
        
    except Exception as e:
        logger.error(f"An error occurred while processing logic for {jid} (Agent {agent_settings.id}): {e}", exc_info=True)


def _process_buffered_message_threaded(jid: str, instance_id: str, evolution_key: str, server_url: str, agent_id: int):
    """
    وظيفة الوسيط الآمنة للـ Threading. تبحث عن الوكيل ثم تستدعي المنطق الأساسي.
    """
    try:
        # البحث عن الوكيل داخل الـ Thread لضمان سلامة الاتصال بقاعدة البيانات
        agent_settings = get_agent_settings_by_id(agent_id)
        
        _process_buffered_message_logic(jid, instance_id, evolution_key, server_url, agent_settings)
        
    except ObjectDoesNotExist:
        logger.critical(f"Agent ID {agent_id} could not be loaded for processing.")
    except Exception as e:
        logger.error(f"Threaded processing failed for Agent {agent_id}: {e}", exc_info=True)



@csrf_exempt
def webhook(request, agent_id: int):
    """
    نقطة الدخول الرئيسية لجميع رسائل الـ Webhook. تستخدم agent_id لتوحيد الوكيل.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        # 1. التحقق من وجود الوكيل قبل معالجة الـ Payload
        # ملاحظة: تم إزالة هذا الاستدعاء لـ agent_settings لتجنب استدعاء قاعدة بيانات متكرر
        # agent_settings = get_agent_settings_by_id(agent_id) 
        
        request_body = json.loads(request.body.decode('utf-8'))
        
        # استخلاص بيانات الاتصال
        instance_id = request_body.get('instance')
        evolution_key = request_body.get('apikey')
        server_url = request_body.get('server_url') 
        
        if not instance_id or not evolution_key or not server_url:
             logger.error("Missing critical instance data in webhook payload.")
             return JsonResponse({'status': 'error', 'message': 'Missing instance data'}, status=400)

        # تجاهل الرسائل المرسلة من البوت نفسه
        if request_body.get('event') != 'messages.upsert' or request_body.get('data', {}).get('key', {}).get('fromMe', False):
            return JsonResponse({'status': 'ignored', 'message': 'Event not processed'}, status=200)

        data = request_body.get('data', {})
        jid = data.get('key', {}).get('remoteJid') or request_body.get('sender')
        push_name = data.get('pushName', 'Unknown')
        message_body = data.get('message', {})
        message_type = data.get('messageType')
        
        if not jid:
            logger.error("JID not found in webhook data.")
            return JsonResponse({'status': 'error', 'message': 'JID not found'}, status=400)

        # تحديث/إنشاء بيانات العميل
        client, created = Client.objects.get_or_create(
            jid=jid,
            defaults={'name': push_name}
        )
        if not created and client.name != push_name:
            client.name = push_name
            client.save()

        user_message_content = None
        image_url = None

        # معالجة أنواع الرسائل
        if message_type in ['conversation', 'extendedTextMessage']:
            user_message_content = message_body.get('conversation') or message_body.get('extendedTextMessage', {}).get('text')
        
        elif message_type == 'imageMessage':
            user_message_content = message_body.get('imageMessage', {}).get('caption')
            image_url = message_body.get('imageMessage', {}).get('url')
        
        elif message_type == 'audioMessage':
            audio_message_data = message_body.get('audioMessage', {})
            base64_data = request_body.get('data', {}).get('message', {}).get('base64')
            mimetype = audio_message_data.get('mimetype', 'audio/ogg')
            
            if base64_data:
                print("✅ Found Base64 audio, starting transcription...")
                user_message_content = transcribe_audio_from_base64(base64_data, mimetype)
            else:
                logger.warning("❌ No Base64 audio found in the payload.")
                user_message_content = "[Audio message, but no Base64 found]"


        if not user_message_content:
            logger.warning(f"Message type '{message_type}' has no valid text content.")
            return JsonResponse({'status': 'unsupported', 'message': 'Cannot process messages without text content at this time.'}, status=200)
            
        # 2. إعداد الـ Debounce Buffer
        buffer_key = f"{jid}:{instance_id}"

        if buffer_key in _user_buffers and _user_buffers[buffer_key]['timer'] and _user_buffers[buffer_key]['timer'].is_alive():
            _user_buffers[buffer_key]['timer'].cancel()
            _user_buffers[buffer_key]['content'] += " " + user_message_content
        else:
            _user_buffers[buffer_key] = {
                'content': user_message_content,
                'message_type': message_type,
                'image_url': image_url,
                'instance_id': instance_id,
                'evolution_key': evolution_key,
                'server_url': server_url
            }

        # 3. إعادة تشغيل الـ Debounce Timer
        # نمرر agent_id لدالة _process_buffered_message_threaded لتقوم بتحميل الوكيل
        new_timer = threading.Timer(
            DEBOUNCE_TIME, 
            _process_buffered_message_threaded, 
            args=[jid, instance_id, evolution_key, server_url, agent_id]
        )
        new_timer.start()
        _user_buffers[buffer_key]['timer'] = new_timer

        return JsonResponse({
            'status': 'success',
            'reply': 'Message received, debounce active.',
            'instance_id': instance_id,
            'agent_id': agent_id
        })
    
    except ObjectDoesNotExist:
         logger.error(f"Attempted to access unknown Agent ID: {agent_id}")
         return JsonResponse({'status': 'error', 'message': f'Agent ID {agent_id} not found.'}, status=404)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON received: {e}")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"An unexpected error occurred in webhook for Agent {agent_id}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'Internal Server Error'}, status=500)