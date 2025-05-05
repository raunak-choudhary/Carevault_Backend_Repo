# routes/appointments.py
from flask import Blueprint, request, jsonify, g
from services.appointment_service import (
    create_appointment,
    get_appointment_by_id,
    get_appointments,
)
from routes.auth import token_required  # Import auth decorator
from datetime import datetime, timedelta

appointments_bp = Blueprint("appointments", __name__, url_prefix="/api/appointments")


# --- Helper Function to Map DB Appointment to Frontend Format ---
def map_appointment_to_frontend(db_appointment_data: dict) -> dict | None:
    """Maps combined appointment & provider data to the frontend structure."""
    if not db_appointment_data:
        return None

    provider_details = db_appointment_data.get("provider_details")

    # Format location string
    location_str = ""
    if provider_details:
        parts = [
            provider_details.get("address"),
            provider_details.get("city"),
            provider_details.get("state"),
            provider_details.get("zip"),
        ]
        location_str = ", ".join(filter(None, parts))  # Join non-empty parts

    # Parse appointment_date and calculate endTime
    start_time_dt = None
    end_time_dt = None
    formatted_start_time = None
    formatted_end_time = None
    formatted_date = None
    appointment_date_iso = db_appointment_data.get("appointment_date")
    duration_minutes = db_appointment_data.get(
        "duration_minutes", 30
    )  # Default if missing

    if appointment_date_iso:
        try:
            # Ensure correct parsing of timestamp with timezone
            start_time_dt = datetime.fromisoformat(
                appointment_date_iso.replace("Z", "+00:00")
            )
            end_time_dt = start_time_dt + timedelta(minutes=duration_minutes)

            # Format for frontend
            formatted_start_time = start_time_dt.isoformat(
                timespec="minutes"
            )  # YYYY-MM-DDTHH:mm
            formatted_end_time = end_time_dt.isoformat(
                timespec="minutes"
            )  # YYYY-MM-DDTHH:mm
            formatted_date = start_time_dt.strftime("%Y-%m-%d")  # YYYY-MM-DD
        except (ValueError, TypeError) as e:
            print(
                f"Error formatting appointment dates for {db_appointment_data.get('id')}: {e}"
            )
            # Keep formatted dates as None if parsing fails

    # Map reminder boolean to string "60" or None (adjust if FE needs boolean)
    reminder_value = "60" if db_appointment_data.get("reminder") else None

    # Extract title (from reason) and potentially type (from notes)
    title = db_appointment_data.get("reason")
    notes = db_appointment_data.get("notes")
    appointment_type = None  # Default
    if notes and notes.startswith("Type: "):
        parts = notes.split(".", 1)
        appointment_type = parts[0].replace("Type: ", "").strip()
        # You might want to remove this prefix from the notes returned to FE
        # notes = parts[1].strip() if len(parts) > 1 else ""

    # Format createdAt timestamp
    created_at_iso = db_appointment_data.get("created_at")
    formatted_created_at = None
    if created_at_iso:
        try:
            created_at_dt = datetime.fromisoformat(
                created_at_iso.replace("Z", "+00:00")
            )
            formatted_created_at = created_at_dt.isoformat(
                timespec="milliseconds"
            ).replace("+00:00", "Z")
        except (ValueError, TypeError):
            formatted_created_at = created_at_iso  # Fallback

    return {
        "id": str(db_appointment_data.get("id")),
        "userId": db_appointment_data.get("user_id"),
        "createdAt": formatted_created_at,
        "status": db_appointment_data.get("status"),
        "title": title,
        "type": appointment_type,  # Extracted from notes or null
        "providerId": db_appointment_data.get("provider_id"),
        "providerName": provider_details.get("name") if provider_details else None,
        "location": location_str if location_str else None,
        "date": formatted_date,
        "startTime": formatted_start_time,
        "endTime": formatted_end_time,
        "notes": notes,  # Return original notes or the modified one without the type prefix
        "reminder": reminder_value,
    }


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


# --- Route: Get Single Appointment ---
@appointments_bp.route("/<string:appointment_id>", methods=["GET"])
@token_required
def get_appointment_route(appointment_id):
    """Get specific appointment details by ID"""
    user_id = g.current_user_profile["id"]

    # Call service to get combined appointment and provider data
    combined_data, status_code = get_appointment_by_id(user_id, appointment_id)

    # Handle response based on status code
    if status_code == 200:
        # Map the combined data to the specific frontend format
        frontend_data = map_appointment_to_frontend(combined_data)
        if frontend_data:
            return (
                jsonify(
                    {
                        "success": True,
                        "error": False,
                        "message": "Appointment details fetched successfully.",
                        "data": frontend_data,
                    }
                ),
                200,
            )
        else:
            # Error during mapping/formatting
            return (
                jsonify(
                    {
                        "success": False,
                        "error": True,
                        "message": "Failed to format appointment data",
                        "data": None,
                    }
                ),
                500,
            )
    elif status_code == 404:
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": "Appointment not found",
                    "data": None,
                }
            ),
            404,
        )
    elif status_code == 403:
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": "Access denied to this appointment",
                    "data": None,
                }
            ),
            403,
        )
    else:  # Handle 500 or other unexpected errors from service
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": "Failed to retrieve appointment details",
                    "data": None,
                }
            ),
            500,
        )


# --- Updated Route: List Appointments ---
@appointments_bp.route("/", methods=["GET"])
@token_required
def list_appointments_route():
    """
    Get list of appointments for the user with filtering ('upcoming',
    'completed', 'cancelled', 'all') and pagination.
    """
    user_id = g.current_user_profile["id"]

    # --- Parse Query Parameters ---
    try:
        skip = int(request.args.get("skip", 0))
        limit = int(request.args.get("limit", 10))
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

    # Get the simplified filter parameter, default to 'all'
    filter_param = request.args.get("filter", "upcoming").lower()

    # Validate filter parameter
    allowed_filters = ["upcoming", "completed", "cancelled", "all"]
    if filter_param not in allowed_filters:
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": f"Invalid filter value. Use one of: {', '.join(allowed_filters)}",
                    "data": None,
                }
            ),
            400,
        )

    # --- Call Service ---
    # Pass the validated filter parameter to the service
    appointments_list, total_count = get_appointments(
        user_id=user_id, skip=skip, limit=limit, filter_type=filter_param
    )

    # --- Format Response ---
    if appointments_list is None:  # Service indicated an error
        return (
            jsonify(
                {
                    "success": False,
                    "error": True,
                    "message": "Failed to retrieve appointments",
                    "data": None,
                }
            ),
            500,
        )

    # Map each appointment to the detailed frontend format
    formatted_appointments = [
        map_appointment_to_frontend(appt) for appt in appointments_list
    ]
    formatted_appointments = [
        appt for appt in formatted_appointments if appt is not None
    ]  # Filter out potential mapping errors

    return (
        jsonify(
            {
                "success": True,
                "error": False,
                "message": "Appointments retrieved successfully.",
                "data": {
                    "appointments": formatted_appointments,
                    "total": total_count,
                    "skip": skip,
                    "limit": limit,
                    "filter": filter_param,  # Optionally return the applied filter
                },
            }
        ),
        200,
    )
