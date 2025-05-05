# routes/chat.py
from flask import Blueprint, request, jsonify, g
from services.chat_service import process_chat_message  # Import service function
from routes.auth import token_required  # Import auth decorator

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")


@chat_bp.route("/message", methods=["POST"])
@token_required
def send_message():
    """Receives a user message, processes it (stores user msg, gets AI response, stores AI msg), returns AI response"""
    user_id = g.current_user_profile["id"]
    data = request.get_json()

    if not data:
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": "Request body must be JSON",
                    "data": None,
                }
            ),
            400,
        )

    # Call the service function
    ai_message_data, response_tuple = process_chat_message(user_id, data)
    error_json, status_code = response_tuple

    # Handle response based on status code from service
    if status_code == 200:
        # Apply success format, returning the AI message data
        return (
            jsonify(
                {
                    "success": True,
                    "error": False,
                    "message": "AI response generated successfully.",
                    # Return the stored AI message object (includes ID, timestamp etc.)
                    # Or just: "data": { "response": ai_message_data.get("message") }
                    "data": ai_message_data,
                }
            ),
            200,
        )
    else:
        # Apply error format
        error_message = (
            error_json.get("error", "Failed to process message")
            if error_json
            else "Failed to process message"
        )
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": error_message,
                    "data": None,
                }
            ),
            status_code,
        )
