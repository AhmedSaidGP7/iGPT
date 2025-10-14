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

logger = logging.getLogger(__name__)

# Debounce configuration
DEBOUNCE_TIME = 2  # فترة انتظار بالثانية لتجميع الرسائل
_user_buffers = {}  # قاموس لتخزين الرسائل المؤقتة لكل مستخدم

# Utility function to send a message back to the client
def send_message_to_client(jid, text, instance_id, evolution_key, server_url):
    """
    يرسل رسالة نصية إلى العميل باستخدام معرف الحالة والمفتاح والخادم الصحيح.
    """
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
        
        logger.info(f"Message sent successfully to {jid} using instance {instance_id} on {server_url}.")
        return response.json()
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending message to {jid}: {e}")
        return None

# --- Main Processing Logic ---
def _process_buffered_message(jid, instance_id, evolution_key, server_url, agent_settings: OpenAISettings):
    """
    It processes the aggregated message after the debounce period ends and sends the response.
    """
    buffer_key = f"{jid}:{instance_id}" # استخدام مفتاح مركب لضمان فصل الأرقام
    
    if buffer_key not in _user_buffers:
        return
        
    user_message_content = _user_buffers[buffer_key]['content']
    message_type = _user_buffers[buffer_key]['message_type']
    image_url = _user_buffers[buffer_key]['image_url']
    
    del _user_buffers[buffer_key]  # تفريغ الـ buffer بعد المعالجة

    # Start of the main logic
    try:
        client = Client.objects.get(jid=jid)
        user_message = Message.objects.create(
            client=client,
            message_type=message_type,
            content=user_message_content,
            image_url=image_url,
        )

        # 🔹 conversation history
        conversation_history = []
        messages = Message.objects.filter(client=client).order_by('-timestamp')[:5]
        for msg in reversed(messages):
            if msg.content:
                try:
                    response = Response.objects.get(message=msg)
                    conversation_history.append({"role": "user", "content": msg.content})
                    conversation_history.append({"role": "assistant", "content": response.content})
                except Response.DoesNotExist:
                    conversation_history.append({"role": "user", "content": msg.content})

        # knowledge base context
        knowledge_base_chunks = list(agent_settings.knowledge_chunks.all())
        user_embedding = get_embeddings(user_message.content)
        similar_questions_info = find_most_similar_question(user_embedding, knowledge_base_chunks)
        context_questions = [item[1].question for item in similar_questions_info]
        
        # generate AI reply
        reply_text = generate_answer(
            user_message.content,
            context_questions,
            conversation_history,
            agent_settings
        )

        Response.objects.create(message=user_message, content=reply_text)
        
        # ✅ التعديل الرابع: تمرير server_url عند إرسال الرد
        send_message_to_client(jid, reply_text, instance_id, evolution_key, server_url)
        
    except Exception as e:
        logger.error(f"An error occurred while processing buffered message for {jid} (Agent {agent_settings.id}): {e}", exc_info=True)


@csrf_exempt
def webhook(request, agent_id):
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        agent_settings = get_agent_settings_by_id(agent_id)
        request_body = json.loads(request.body.decode('utf-8'))
        logger.info(f"Received webhook data: {request_body}")
        print("📩 Incoming Webhook Payload:", json.dumps(request_body, indent=2, ensure_ascii=False))

        event = request_body.get('event')
        
        # ✅ التعديل الخامس: استخراج server_url من الـ payload
        instance_id = request_body.get('instance')
        evolution_key = request_body.get('apikey')
        server_url = request_body.get('server_url') # استخلاص Server URL
        
        # ✅ التعديل السادس: تحديث فحص البيانات المفقودة
        if not instance_id or not evolution_key or not server_url:
             logger.error("Instance ID, API Key, or Server URL not found in webhook payload.")
             return JsonResponse({'status': 'error', 'message': 'Missing instance data'}, status=400)

        if event != 'messages.upsert' or request_body.get('data', {}).get('key', {}).get('fromMe', False):
            return JsonResponse({'status': 'ignored', 'message': 'Event not processed'}, status=200)

        data = request_body.get('data', {})
        jid = data.get('key', {}).get('remoteJid') or request_body.get('sender')
        push_name = data.get('pushName', 'Unknown')
        message_body = data.get('message', {})
        message_type = data.get('messageType')
        
        if not jid:
            logger.error("JID not found in webhook data.")
            return JsonResponse({'status': 'error', 'message': 'JID not found'}, status=400)

        # ... (Client setup remains the same)
        client, created = Client.objects.get_or_create(
            jid=jid,
            defaults={'name': push_name}
        )
        if not created and client.name != push_name:
            client.name = push_name
            client.save()

        user_message_content = None
        image_url = None
        voice_note_url = None

        if message_type in ['conversation', 'extendedTextMessage']:
            user_message_content = message_body.get('conversation') or message_body.get('extendedTextMessage', {}).get('text')
        
        elif message_type == 'imageMessage':
            user_message_content = message_body.get('imageMessage', {}).get('caption')
            image_url = message_body.get('imageMessage', {}).get('url')
        
        elif message_type == 'audioMessage':
            audio_message_data = message_body.get('audioMessage', {})
            base64_data = request_body.get('data', {}).get('message', {}).get('base64')
            mimetype = audio_message_data.get('mimetype', 'audio/ogg')
            voice_note_url = audio_message_data.get('url')
            
            if base64_data:
                print("✅ Found Base64 audio, starting transcription...")
                user_message_content = transcribe_audio_from_base64(base64_data, mimetype)
            else:
                logger.warning("❌ No Base64 audio found in the payload.")
                user_message_content = "[Audio message, but no Base64 found]"

        if not user_message_content:
            logger.warning(f"Message type '{message_type}' has no valid text content.")
            return JsonResponse({'status': 'unsupported', 'message': 'Cannot process messages without text content at this time.'}, status=200)
            
        # ✅ التعديل هنا: استخدام مفتاح مركب للـ buffer
        buffer_key = f"{jid}:{instance_id}"

        if buffer_key in _user_buffers and _user_buffers[buffer_key]['timer'] and _user_buffers[buffer_key]['timer'].is_alive():
            # إذا كان فيه رسالة سابقة، بنلغي الـ timer وبنضيف المحتوى للرسالة القديمة
            print("⏳ Debounce active: Appending new message content.")
            _user_buffers[buffer_key]['timer'].cancel()
            _user_buffers[buffer_key]['content'] += " " + user_message_content
        else:
            # لو دي أول رسالة أو الرسالة السابقة قديمة، بنبدأ رسالة جديدة في الـ buffer
            print("🚀 Starting new message buffer.")
            _user_buffers[buffer_key] = {
                'content': user_message_content,
                'message_type': message_type,
                'image_url': image_url,
                # ✅ التعديل السابع: حفظ server_url داخل الـ buffer
                'instance_id': instance_id,
                'evolution_key': evolution_key,
                'server_url': server_url
            }

        # ✅ التعديل الثامن: تمرير server_url عند بدء الـ timer
        new_timer = threading.Timer(
            DEBOUNCE_TIME, 
            _process_buffered_message, 
            args=[jid, instance_id, evolution_key, server_url]
        )
        new_timer.start()
        _user_buffers[buffer_key]['timer'] = new_timer

        return JsonResponse({
            'status': 'success',
            'reply': 'Message received and waiting for more input (debounce active).',
            'instance_id': instance_id
        })
    
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON received: {e}")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'Internal Server Error'}, status=500)
