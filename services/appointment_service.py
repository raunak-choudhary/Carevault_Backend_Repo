# services/appointment_service.py
from supabase_client import get_supabase
from datetime import datetime, timedelta, time


supabase = get_supabase()


def create_appointment(user_id: str, data: dict):
    """
    Creates a new appointment record for the user.
    Returns: Tuple (appointment_data | None, status_code)
    Status codes: 201 (Created), 400 (Bad Request), 404 (Provider Not Found), 500 (Error)
    """
    # --- Extract and Validate Input ---
    provider_id = data.get("providerId")
    date_str = data.get("date")  # YYYY-MM-DD
    time_slot_str = data.get("time_slot")  # HH:mm
    title = data.get("title")  # Will map to 'reason' field

    if not provider_id or not date_str or not time_slot_str or not title:
        return None, (
            {"error": "Missing required fields: providerId, date, time_slot, title"},
            400,
        )

    # --- Verify Provider Exists ---
    try:
        provider_response = (
            supabase.table("providers")
            .select("id")
            .eq("id", provider_id)
            .maybe_single()
            .execute()
        )
        # maybe_single() returns None if not found, raises error on multiple (shouldn't happen with ID)
        if not provider_response.data:
            return None, ({"error": f"Provider with ID '{provider_id}' not found"}, 404)
    except Exception as e:
        print(f"DB Error checking provider {provider_id}: {str(e)}")
        return None, ({"error": "Failed to verify provider"}, 500)

    # --- Combine Date and Time, Calculate Duration ---
    try:
        # Combine date and time string
        full_datetime_str = f"{date_str} {time_slot_str}:00"  # Add seconds
        # Parse into datetime object (assuming local time initially, needs timezone handling if critical)
        appointment_dt = datetime.strptime(full_datetime_str, "%Y-%m-%d %H:%M:%S")
        # Convert to ISO format string for Supabase (timestamptz prefers ISO 8601)
        appointment_iso = appointment_dt.isoformat()
        # Duration is fixed at 30 mins per user request
        duration_minutes = 30
    except ValueError:
        return None, (
            {"error": "Invalid date or time_slot format. Use YYYY-MM-DD and HH:mm"},
            400,
        )

    # --- Map other fields ---
    notes = data.get("notes")
    # If 'type' field exists and needs storing, add it to notes or another field
    appointment_type = data.get("type")
    final_notes = (
        f"Type: {appointment_type}. {notes}"
        if appointment_type and notes
        else appointment_type or notes
    )

    # Interpret reminder field ("60" likely means True)
    reminder_input = data.get("reminder")
    reminder_bool = (
        reminder_input is not None
    )  # Treat any value provided as enabling reminder

    # Default status
    status = "scheduled"

    # --- Prepare DB Data ---
    db_data = {
        "user_id": user_id,
        "provider_id": provider_id,
        "appointment_date": appointment_iso,
        "duration_minutes": duration_minutes,
        "reason": title,  # Mapping title to reason
        "notes": final_notes,
        "status": status,
        "reminder": reminder_bool,
        "type": appointment_type,
    }

    # --- Insert into Database ---
    try:
        response = supabase.table("appointments").insert(db_data).execute()
        if not response.data:
            return None, ({"error": "Failed to create appointment"}, 500)

        created_appointment = response.data[0]
        return created_appointment, (None, 201)  # Return data and success status

    except Exception as e:
        print(f"DB Error creating appointment: {str(e)}")
        # Could check for specific DB errors like unique constraints if needed
        return None, ({"error": f"Failed to create appointment: {str(e)}"}, 500)
