import json
import logging
import requests
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from .models import Client, Message, Response
from .rag_utilities import get_embeddings, find_most_similar_question, generate_answer, transcribe_audio_from_base64
from knowledge.models import KnowledgeBase

logger = logging.getLogger(__name__)

# Utility function to send a message back to the client
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

# New utility function to fetch media from its ID
def get_media_from_id(media_id, media_type):
    """
    Fetches a media file (audio or image) from the external server using its ID.
    Returns the base64 encoded data.
    """
    try:
        url = f"{settings.SERVER_URL}/media/download/{settings.INSTANCE_ID}"
        headers = {
            "apikey": settings.EVOLUTION_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "id": media_id,
            "full": True # We need the full base64 data
        }
        
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        
        # The base64 data is usually nested inside the "data" key of the response
        if 'data' in data and 'base64' in data['data']:
            logger.info(f"Media data for ID {media_id} fetched successfully.")
            return data['data']['base64']
        else:
            logger.error(f"Base64 data not found in media response for ID: {media_id}")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching media for ID {media_id}: {e}")
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
        print("📩 Incoming Webhook Payload:", json.dumps(request_body, indent=2, ensure_ascii=False))

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

        user_message_content = None
        voice_note_url = None
        image_url = None

        if message_type in ['conversation', 'extendedTextMessage']:
            user_message_content = message_body.get('conversation') or message_body.get('extendedTextMessage', {}).get('text')
        elif message_type == 'imageMessage':
            user_message_content = message_body.get('imageMessage', {}).get('caption')
            image_url = message_body.get('imageMessage', {}).get('url')
            # Extract media ID from 'query' field if present
            media_query = message_body.get('imageMessage', {}).get('query')
            if media_query:
                try:
                    media_id = media_query.split('|')[1]
                    logger.info(f"Image ID found: {media_id}")
                    # You can fetch the base64 data here if needed for processing
                    # image_base64 = get_media_from_id(media_id, 'image')
                except IndexError:
                    logger.error(f"Invalid image query format: {media_query}")
        
        elif message_type == 'audioMessage':
            audio_message_data = message_body.get('audioMessage', {})
            voice_note_url = audio_message_data.get('url')
            
            # Check for direct base64 data first (older method)
            base64_audio_data = audio_message_data.get('base64')
            
            if not base64_audio_data:
                # Check for 'query' field to get media ID (new method)
                media_query = audio_message_data.get('query')
                if media_query:
                    print("Found 'query' field in audio message.")
                    try:
                        # Extract the media ID from the query string
                        media_id = media_query.split('|')[1]
                        logger.info(f"Audio ID found: {media_id}. Attempting to fetch base64 data.")
                        
                        # Fetch the base64 data using the ID
                        base64_audio_data = get_media_from_id(media_id, 'audio')
                        
                        if base64_audio_data:
                             logger.info("Base64 data fetched successfully using ID.")
                        else:
                             logger.error("Failed to fetch base64 data using ID.")
                    except IndexError:
                        logger.error(f"Invalid audio query format: {media_query}")
                        base64_audio_data = None
            
            if base64_audio_data:
                print("Using Base64 data for transcription.")
                user_message_content = transcribe_audio_from_base64(base64_audio_data)
                if not user_message_content:
                    logger.error("Transcription failed for the fetched audio data.")
            
            if not user_message_content:
                logger.error("Base64 audio data not found or transcription failed.")
                send_message_to_client(jid, "Sorry, the voice note data was not received correctly. Can you please try again?")
                return JsonResponse({'status': 'error', 'message': 'Base64 audio data not found or transcription failed'}, status=500)
        
        # Check if the message contains valid content
        if not user_message_content:
            logger.warning(f"Message type '{message_type}' has no valid text content.")
            return JsonResponse({'status': 'unsupported', 'message': 'Cannot process messages without text content at this time.'}, status=200)
            
        # Create the Message object for all types
        user_message = Message.objects.create(
            client=client,
            message_type=message_type,
            content=user_message_content,
            image_url=image_url,
            voice_note_url=voice_note_url
        )

        # Retrieve conversation history
        conversation_history = []
        messages = Message.objects.filter(client=client).order_by('-timestamp')[:5]
        for msg in reversed(messages):
            # Check for empty content to avoid OpenAI errors
            if msg.content:
                try:
                    response = Response.objects.get(message=msg)
                    conversation_history.append({"role": "user", "content": msg.content})
                    conversation_history.append({"role": "assistant", "content": response.content})
                except Response.DoesNotExist:
                    conversation_history.append({"role": "user", "content": msg.content})

        # Process the message and generate a response
        knowledge_base_chunks = list(KnowledgeBase.objects.all())
        user_embedding = get_embeddings(user_message.content)
        
        similar_questions_info = find_most_similar_question(user_embedding, knowledge_base_chunks)
        
        # Use the question strings from the found objects
        context_questions = [item[1].question for item in similar_questions_info]
        
        # Generate the final answer using RAG
        reply_text = generate_answer(
            user_message.content,
            context_questions,
            conversation_history
        )

        # Save assistant's response to the database
        Response.objects.create(message=user_message, content=reply_text)

        # Send the response back to the client
        send_message_to_client(jid, reply_text)

        return JsonResponse({'status': 'success', 'reply': reply_text})
    
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON received: {e}")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'Internal Server Error'}, status=500)
