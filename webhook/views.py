import json
import logging
import requests
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from .models import Client, Message, Response
from .rag_utilities import (
    get_embeddings,
    find_most_similar_question,
    generate_answer,
    transcribe_audio_from_base64, # ✅ تم استيراد الدالة الجديدة
)
from knowledge.models import KnowledgeBase

logger = logging.getLogger(__name__)

# Utility function to send a message back to the client
def send_message_to_client(jid, text):
    try:
        url = f"{settings.SERVER_URL}/message/sendText/{settings.INSTANCE_ID}"
        headers = {
            "apikey": settings.EVOLUTION_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "number": jid.split('@')[0],
            "text": text,
            "delay": 8000,
            "linkPreview": True,
        }
        
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        logger.info(f"Message sent successfully to {jid}.")
        return response.json()
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending message to {jid}: {e}")
        return None


@csrf_exempt
def webhook(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        request_body = json.loads(request.body.decode('utf-8'))
        logger.info(f"Received webhook data: {request_body}")
        print("📩 Incoming Webhook Payload:", json.dumps(request_body, indent=2, ensure_ascii=False))

        event = request_body.get('event')
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

        client, created = Client.objects.get_or_create(
            jid=jid,
            defaults={'name': push_name}
        )
        if not created and client.name != push_name:
            client.name = push_name
            client.save()

        user_message_content = None
        base64_data = None
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
                # ✅ الخطوة الجديدة: تحويل الـ Base64 إلى نص باستخدام دالة Transcribe
                print("✅ Found Base64 audio, starting transcription...")
                user_message_content = transcribe_audio_from_base64(base64_data, mimetype)
            else:
                logger.warning("❌ No Base64 audio found in the payload.")
                user_message_content = "[Audio message, but no Base64 found]"

        if not user_message_content:
            logger.warning(f"Message type '{message_type}' has no valid text content.")
            return JsonResponse({'status': 'unsupported', 'message': 'Cannot process messages without text content at this time.'}, status=200)
            
        user_message = Message.objects.create(
            client=client,
            message_type=message_type,
            content=user_message_content,
            image_url=image_url,
            voice_note_url=voice_note_url
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

        # 🔹 knowledge base context
        knowledge_base_chunks = list(KnowledgeBase.objects.all())
        user_embedding = get_embeddings(user_message.content)
        similar_questions_info = find_most_similar_question(user_embedding, knowledge_base_chunks)
        context_questions = [item[1].question for item in similar_questions_info]
        
        # 🔹 generate AI reply
        reply_text = generate_answer(
            user_message.content,
            context_questions,
            conversation_history
        )

        Response.objects.create(message=user_message, content=reply_text)
        send_message_to_client(jid, reply_text)

        return JsonResponse({
            'status': 'success',
            'reply': reply_text,
            'base64': base64_data
        })
    
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON received: {e}")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'Internal Server Error'}, status=500)
