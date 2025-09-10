import json
import logging
import requests
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from .models import Client, Message, Response
from .rag_utilities import get_embeddings, find_most_similar_question, generate_answer
from knowledge.models import KnowledgeBase

logger = logging.getLogger(__name__)

# Utility to send a message back to the client via an external API
def send_message_to_client(jid, text):
    """
    Sends a text message to a client using the specified external API.
    """
    try:
        url = f"{settings.SERVER_URL}/message/sendText/{settings.INSTANCE_ID}"
        headers = {
            "apikey": settings.EVOLUTION_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "number": jid.split('@')[0],  # Extracting phone number from JID
            "text": text,
            "delay": 8000,
            "linkPreview": True,
        }
        
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status() # Raise an exception for bad status codes
        
        logger.info(f"Message sent successfully to {jid}.")
        return response.json()
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending message to {jid}: {e}")
        return None

@csrf_exempt
def webhook(request):
    """
    Handles incoming webhook requests from the messaging platform.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        request_body = json.loads(request.body.decode('utf-8'))
        logger.info(f"Received webhook data: {request_body}")

        event = request_body.get('event')
        
        # We only want to process incoming user messages, not server acks or outgoing messages
        if event != 'messages.upsert' or request_body.get('data', {}).get('key', {}).get('fromMe', False):
            return JsonResponse({'status': 'ignored', 'message': 'Event not processed'}, status=200)

        # Extract message details
        data = request_body.get('data', {})
        jid = data.get('key', {}).get('remoteJid') or request_body.get('sender')
        push_name = data.get('pushName', 'Unknown')
        message_body = data.get('message', {})
        message_type = data.get('messageType')
        
        if not jid:
            logger.error("JID not found in webhook data.")
            return JsonResponse({'status': 'error', 'message': 'JID not found'}, status=400)

        # Get or create client
        client, created = Client.objects.get_or_create(
            jid=jid,
            defaults={'name': push_name}
        )
        if not created and client.name != push_name:
            client.name = push_name
            client.save()

        # Handle different message types
        user_message = None
        if message_type == 'conversation' or message_type == 'extendedTextMessage':
            content = message_body.get('conversation') or message_body.get('extendedTextMessage', {}).get('text')
            if content:
                user_message = Message.objects.create(
                    client=client,
                    message_type='text',
                    content=content
                )
        elif message_type == 'imageMessage':
            caption = message_body.get('imageMessage', {}).get('caption')
            imageUrl = message_body.get('imageMessage', {}).get('url')
            user_message = Message.objects.create(
                client=client,
                message_type='image',
                content=caption,
                image_url=imageUrl
            )
        elif message_type == 'audioMessage':
            voiceUrl = message_body.get('audioMessage', {}).get('url')
            user_message = Message.objects.create(
                client=client,
                message_type='voice',
                voice_note_url=voiceUrl
            )

        if not user_message:
            logger.warning(f"Unsupported message type: {message_type}")
            return JsonResponse({'status': 'unsupported', 'message': 'Unsupported message type'}, status=200)

        # Retrieve conversation history
        conversation_history = []
        messages = Message.objects.filter(client=client).order_by('-timestamp')[:5]
        for msg in reversed(messages):
            try:
                response = Response.objects.get(message=msg)
                conversation_history.append({"role": "user", "content": msg.content})
                conversation_history.append({"role": "assistant", "content": response.content})
            except Response.DoesNotExist:
                conversation_history.append({"role": "user", "content": msg.content})

        # Process the message and generate a response
        if user_message.message_type == 'text' and user_message.content:
            knowledge_base_chunks = list(KnowledgeBase.objects.all())
            user_embedding = get_embeddings(user_message.content)
            
            similar_questions_info = find_most_similar_question(user_embedding, knowledge_base_chunks)
            
            # Generate the final answer using RAG
            reply_text = generate_answer(
                user_message.content,
                similar_questions_info,
                conversation_history
            )

            # Save assistant's response to the database
            Response.objects.create(message=user_message, content=reply_text)

            # Send the response back to the client
            send_message_to_client(jid, reply_text)

            return JsonResponse({'status': 'success', 'reply': reply_text})
        else:
            return JsonResponse({'status': 'unsupported', 'message': 'Cannot process non-text messages at this time.'}, status=200)
    
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON received: {e}")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'Internal Server Error'}, status=500)
