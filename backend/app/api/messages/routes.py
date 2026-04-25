"""
Message endpoints - the core AI interaction.

Educational Note: This is where the magic happens! When a user sends a message,
the chat domain's public surface orchestrates:

1. Context Building:
   - Loads project sources (with summaries)
   - Loads user and project memory
   - Builds dynamic system prompt

2. Claude API Call:
   - Sends conversation history + context
   - Provides tools: search_sources, store_memory

3. Tool Use Loop (Agentic Pattern):
   - Claude may call search_sources to query embeddings
   - Claude may call store_memory to save important info
   - Loop continues until Claude returns final text response

4. Response Handling:
   - Stores both user and assistant messages
   - Returns formatted response with citations

Routes:
- POST /projects/<id>/chats/<id>/messages - Send message, get AI response
- POST /projects/<id>/chats/<id>/messages/stream - Send message, stream AI response
"""
import json

from flask import jsonify, request, current_app, Response, stream_with_context

from app import chat
from app.api.messages import messages_bp
from app.auth.identity import get_request_identity


def _format_sse(event_name: str, payload: dict | None = None) -> str:
    """Format a single SSE event chunk."""
    data = json.dumps(payload or {}, ensure_ascii=False)
    return f"event: {event_name}\ndata: {data}\n\n"


@messages_bp.route('/projects/<project_id>/chats/<chat_id>/messages', methods=['POST'])
def send_message(project_id, chat_id):
    """
    Send a message in a chat and get AI response.

    Educational Note: This endpoint is kept thin - the chat public surface
    handles:
    1. Storing user message
    2. Building context with system prompt
    3. Calling Claude API
    4. Executing tool use loop
    5. Storing assistant response
    6. Syncing chat index

    Request Body:
        { "message": "Your question about the sources..." }

    Response:
        {
            "success": true,
            "user_message": { ... message object ... },
            "assistant_message": { ... message object with citations ... }
        }
    """
    try:
        data = request.get_json()

        if not data or 'message' not in data:
            return jsonify({
                'success': False,
                'error': 'Message is required'
            }), 400

        identity = get_request_identity()
        result = chat.send(
            project_id=project_id,
            chat_id=chat_id,
            message=data['message'],
            identity=identity,
        )

        return jsonify({
            'success': True,
            'user_message': result['user_message'],
            'assistant_message': result['assistant_message'],
        }), 200

    except ValueError as e:
        # Chat or project not found
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404
    except Exception as e:
        current_app.logger.exception("Error sending message")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@messages_bp.route('/projects/<project_id>/chats/<chat_id>/messages/stream', methods=['POST'])
def stream_message(project_id, chat_id):
    """
    Send a message in a chat and stream back assistant deltas as SSE.

    The final saved assistant message is emitted as an `assistant_done` event.
    """
    data = request.get_json()

    if not data or 'message' not in data:
        return jsonify({
            'success': False,
            'error': 'Message is required'
        }), 400

    user_message_text = data['message']
    identity = get_request_identity()

    def generate():
        for event in chat.stream(
            project_id=project_id,
            chat_id=chat_id,
            message=user_message_text,
            identity=identity,
        ):
            yield _format_sse(event['event'], event['data'])

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return Response(stream_with_context(generate()), headers=headers)
