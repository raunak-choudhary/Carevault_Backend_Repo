# routes/appointments.py
from flask import Blueprint, request, jsonify, g
from services.appointment_service import create_appointment  # Import service function
from routes.auth import token_required  # Import auth decorator

appointments_bp = Blueprint("appointments", __name__, url_prefix="/api/appointments")


@appointments_bp.route("/", methods=["POST"])
@token_required
def add_appointment_route():
    """Create a new appointment"""
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
    created_appointment, response_tuple = create_appointment(user_id, data)
    error_json, status_code = response_tuple

    # Handle response based on status code from service
    if status_code == 201:
        # Apply success format
        return (
            jsonify(
                {
                    "success": True,
                    "error": False,
                    "message": "Appointment created successfully.",
                    "data": created_appointment,  # Return DB object for now
                }
            ),
            201,
        )
    else:
        # Apply error format
        error_message = (
            error_json.get("error", "Failed to create appointment")
            if error_json
            else "Failed to create appointment"
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
