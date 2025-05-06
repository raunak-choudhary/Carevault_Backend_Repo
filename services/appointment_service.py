# services/appointment_service.py
from supabase_client import get_supabase
from datetime import datetime, timedelta, time, timezone


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
    time_slot_str = data.get("startTime")  # HH:mm
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


# --- New Service Function: Get Appointment by ID ---
def get_appointment_by_id(user_id: str, appointment_id: str):
    """
    Fetches a single appointment by ID with provider details, ensuring user ownership.
    Returns: Tuple (combined_data | None, status_code)
    Status codes: 200 (OK), 404 (Not Found), 403 (Forbidden), 500 (Error)
    """
    try:
        # Fetch appointment details
        appt_response = (
            supabase.table("appointments")
            .select("*")
            .eq("id", appointment_id)
            .maybe_single()
            .execute()
        )

        if not appt_response.data:
            return None, 404  # Appointment not found

        appointment = appt_response.data

        # Check ownership
        if appointment.get("user_id") != user_id:
            return None, 403  # Forbidden access

        # Fetch associated provider details
        provider_data = None

        provider_id = appointment.get("provider_id")

        if provider_id:
            prov_response = (
                supabase.table("providers")
                .select("*")
                .eq("id", provider_id)
                .maybe_single()
                .execute()
            )
            if prov_response.data:
                provider_data = prov_response.data
            else:
                # Provider associated with appointment not found (data integrity issue?)
                print(
                    f"Warning: Provider ID {provider_id} found in appointment {appointment_id} but not in providers table."
                )
                # Decide how to handle: return error, return partial data, etc.
                # For now, we'll proceed but provider details will be missing/null

        # Combine appointment data with provider data (if found)
        combined_data = appointment
        combined_data["provider_details"] = (
            provider_data  # Add provider data under a specific key
        )

        return combined_data, 200

    except Exception as e:
        print(f"DB Error fetching appointment {appointment_id}: {str(e)}")
        return None, 500  # Internal Server Error


# --- Service Function: List Appointments with Simplified Filter ---
def get_appointments(
    user_id: str, skip: int, limit: int, filter_type: str | None = None
):
    """
    Fetches a list of appointments for a user with simplified filtering.
    filter_type can be 'upcoming', 'completed', 'cancelled', or 'all'.
    Returns: Tuple (list_of_combined_data | None, total_count | 0)
    """
    try:
        # Base query
        query = (
            supabase.table("appointments")
            .select("*", count="exact")
            .eq("user_id", user_id)
        )

        # Default ordering
        order_column = "appointment_date"
        order_desc = True  # Show most recent first by default

        # Apply filters based on filter_type
        filter_type_lower = filter_type.lower() if filter_type else "all"

        if filter_type_lower == "upcoming":
            now_utc = datetime.now(timezone.utc)
            query = query.gte("appointment_date", now_utc.isoformat())
            # Also commonly filter by status for upcoming, e.g., only 'scheduled'
            query = query.eq("status", "scheduled")
            order_desc = False  # Show soonest first
        elif filter_type_lower == "completed":
            query = query.eq("status", "completed")
        elif filter_type_lower == "cancelled":
            query = query.eq("status", "cancelled")
        # elif filter_type_lower == 'all':
        # No additional status/date filters needed
        # else: # Default to 'all' if filter is invalid
        # No additional filters

        # Apply ordering and pagination
        query = query.order(order_column, desc=order_desc).range(skip, skip + limit - 1)

        # Execute query
        response = query.execute()

        appointments = response.data
        total = (
            response.count
            if hasattr(response, "count") and response.count is not None
            else len(appointments)
        )

        # --- Fetch provider details efficiently (same as before) ---
        combined_results = []
        provider_ids = {
            appt.get("provider_id") for appt in appointments if appt.get("provider_id")
        }
        provider_map = {}
        if provider_ids:
            prov_response = (
                supabase.table("providers")
                .select("*")
                .in_("id", list(provider_ids))
                .execute()
            )
            if prov_response.data:
                provider_map = {prov["id"]: prov for prov in prov_response.data}

        for appt in appointments:
            provider_id = appt.get("provider_id")
            appt["provider_details"] = provider_map.get(provider_id)
            combined_results.append(appt)
        # -----------------------------------------------

        return combined_results, total

    except Exception as e:
        print(f"DB Error listing appointments for user {user_id}: {str(e)}")
        return None, 0
