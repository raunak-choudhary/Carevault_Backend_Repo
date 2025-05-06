# routes/chat.py
from flask import Blueprint, request, jsonify, g
from services.chat_service import (
    process_chat_message,
    get_chat_history,
    process_uploaded_document,
)
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


@chat_bp.route("/", methods=["GET"])  # Route is /api/v1/chat/
@token_required
def list_chat_history_route():
    """Get paginated chat message history for the user"""
    user_id = g.current_user_profile["id"]

    # --- Parse Query Parameters for Pagination ---
    try:
        skip = int(request.args.get("skip", 0))
        # Default limit to 50, as history can be long
        limit = int(request.args.get("limit", 50))
        if limit > 200:  # Add a max limit for safety
            limit = 200
    except ValueError:
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": "Invalid skip or limit parameter",
                    "data": None,
                }
            ),
            400,
        )

    # --- Call Service ---
    messages_list, total_count = get_chat_history(user_id=user_id)

    # --- Format Response ---
    if messages_list is None:  # Service indicated an error
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": "Failed to retrieve chat history",
                    "data": None,
                }
            ),
            500,
        )

    # Use the standard success response format
    return (
        jsonify(
            {
                "success": True,
                "error": False,
                "message": "Chat history retrieved successfully.",
                "data": {
                    "messages": messages_list,  # List of message objects from DB
                    "total": total_count,
                    "skip": skip,
                    "limit": limit,
                },
            }
        ),
        200,
    )


@chat_bp.route("/upload", methods=["POST"])
@token_required
def upload_and_process_document_via_chat():
    """
    Receives a file via chat, triggers analysis and storage via service.
    """
    user_id = g.current_user_profile["id"]
    auth_header = request.headers.get("Authorization")
    user_token = (
        auth_header.split()[1] if auth_header and len(auth_header.split()) > 1 else None
    )

    if not user_token:
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": "Auth token missing or invalid",
                    "data": None,
                }
            ),
            401,
        )

    if "file" not in request.files:
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": "No file part",
                    "data": None,
                }
            ),
            400,
        )

    file = request.files["file"]
    if not file or not file.filename:
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": "No selected file",
                    "data": None,
                }
            ),
            400,
        )

    # Call the service function to handle all processing
    result_data, status_code = process_uploaded_document(user_id, user_token, file)

    # Format the final response based on service outcome
    if status_code < 400:  # Success (e.g., 200 or 201)
        return (
            jsonify(
                {
                    "success": True,
                    "error": False,
                    "message": f"Document '{result_data.get('title', 'Unknown')}' analyzed and saved.",
                    "data": result_data,
                }
            ),
            status_code,
        )
    else:  # Error
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": result_data.get(
                        "error", "An unknown error occurred during processing."
                    ),
                    "data": None,
                }
            ),
            status_code,
        )
