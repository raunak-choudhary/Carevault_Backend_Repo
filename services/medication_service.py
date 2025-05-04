# services/medication_service.py
from supabase_client import get_supabase
from datetime import datetime
import json
from flask import (
    jsonify,
)

supabase = get_supabase()


# Function to handle the core logic of adding a medication
def create_medication_reminder(user_id: str, data: dict):

    # --- Validation and Data Mapping Logic ---

    medication_name = data.get("name")
    frequency = data.get("frequency")
    dosage_schedule = data.get("dosageSchedule")

    if not medication_name or not frequency or dosage_schedule is None:
        # Option 1: Raise an exception for the route to catch
        # raise ValueError("Missing required fields: name, frequency, dosageSchedule")
        # Option 2: Return error tuple for route to handle
        return None, (
            {"error": "Missing required fields: name, frequency, dosageSchedule"},
            400,
        )

    dosage = data.get("dosage")
    dosage_unit = data.get("unit")
    notes_list = [data.get("notes")]
    if data.get("instructions"):
        notes_list.append(f"Instructions: {data.get('instructions')}")
    if data.get("prescribedBy"):
        notes_list.append(f"Prescribed By: {data.get('prescribedBy')}")
    if data.get("pharmacy"):
        notes_list.append(f"Pharmacy: {data.get('pharmacy')}")
    final_notes = ". ".join(filter(None, notes_list))

    end_date_str = data.get("refillDate")

    try:
        start_date = datetime.now().date()

        end_date = (
            datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str else None
        )
    except ValueError:
        # return None, ({"error": "Invalid date format. Use YYYY-MM-DD"}, 400)
        raise ValueError("Invalid date format. Use YYYY-MM-DD")

    is_active = data.get("status", "active").lower() == "active"

    db_data = {
        "user_id": user_id,
        "medication_name": medication_name,
        "dosage": dosage,
        "dosage_unit": dosage_unit,
        "frequency": frequency,
        "times_of_day": (
            json.dumps(dosage_schedule)
            if isinstance(dosage_schedule, list)
            else dosage_schedule
        ),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat() if end_date else None,
        "notes": final_notes,
        "active": is_active,
    }

    # --- End Validation and Mapping ---

    try:
        response = supabase.table("medications").insert(db_data).execute()
        if not response.data:
            # return None, ({"error": "Failed to add medication reminder"}, 500)
            raise Exception("Database insert failed, no data returned")

        created_medication = response.data[0]

        return created_medication, None  # Return data and None for error

    except Exception as e:
        print(f"DB Error adding medication: {str(e)}")  # Log in service
        # Raise a more specific exception or return error tuple
        # raise e # Let the route handler catch it
        return None, ({"error": f"Failed to add medication: {str(e)}"}, 500)


# --- New Service Function: Get Medication by ID ---
def get_medication_by_id(user_id: str, medication_id: str):
    """
    Fetches a single medication reminder by ID, ensuring user ownership.
    Returns: Tuple (medication_data | None, status_code)
    Status codes: 200 (OK), 404 (Not Found), 403 (Forbidden), 500 (Error)
    """
    try:

        response = (
            supabase.table("medications").select("*").eq("id", medication_id).execute()
        )

        if not response.data:
            # Medication not found
            return None, 404

        medication = response.data[0]

        # Check ownership
        if medication.get("user_id") != user_id:
            # User does not own this record
            return None, 403

        # Found and owned by user

        medication["times_of_day"] = json.loads(
            medication["times_of_day"]
        )  # Convert JSON string back to list

        return medication, 200

    except Exception as e:
        # Catch any other unexpected errors during DB query
        print(f"DB Error fetching medication {medication_id}: {str(e)}")
        return None, 500  # Internal Server Error
        # Catch any other unexpected errors during DB query
        print(f"DB Error fetching medication {medication_id}: {str(e)}")
        raise Exception(
            f"Failed to retrieve medication: {str(e)}"
        )  # Raise a generic exception


def get_medications(
    user_id: str,
    skip: int = 0,
    limit: int = 10,
    title_filter: str | None = None,
    active_filter: bool | None = None,
):
    """
    Fetches a list of medication reminders for a user with filtering and specific columns.
    Returns: Tuple (list_of_medications | None, total_count | 0)
    """
    try:
        # Select only the required columns + id for potential keys
        select_columns = "id, medication_name, dosage, dosage_unit, frequency, times_of_day, notes, end_date, active"

        query = (
            supabase.table("medications")
            .select(select_columns, count="exact")
            .eq("user_id", user_id)
        )

        # Apply filters
        if title_filter:
            # Use ilike for case-insensitive partial matching on medication_name
            query = query.ilike("medication_name", f"%{title_filter}%")

        if active_filter is not None:  # Check specifically for True or False
            query = query.eq("active", active_filter)

        # Apply ordering and pagination
        query = query.order("medication_name", desc=False).range(skip, skip + limit - 1)

        response = query.execute()

        # Get data and total count
        medications = response.data

        for medication in medications:
            medication["times_of_day"] = json.loads(
                medication["times_of_day"]
            )  # Convert JSON string back to list

        total = (
            response.count
            if hasattr(response, "count") and response.count is not None
            else len(response.data)
        )

        return medications, total

    except Exception as e:
        print(f"DB Error listing medications for user {user_id}: {str(e)}")
        return None, 0  # Return None and 0 count on error
