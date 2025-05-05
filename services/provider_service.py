# services/provider_service.py
from supabase_client import get_supabase

PROVIDERS_TABLE = "providers"  # Assumes schema modified as discussed
supabase = get_supabase()


def get_providers(
    skip: int,
    limit: int,
    specialty_filter: str | None = None,
    name_filter: str | None = None,
):
    """
    Fetches a list of providers with optional filtering and pagination.
    Returns: Tuple (list_of_providers | None, total_count | 0)
    """
    try:
        query = supabase.table(PROVIDERS_TABLE).select("*", count="exact")

        # Apply filters
        if specialty_filter:
            query = query.eq("specialty", specialty_filter)
        if name_filter:
            query = query.ilike(
                "name", f"%{name_filter}%"
            )  # Case-insensitive partial match

        # Apply ordering and pagination
        query = query.order("name", desc=False).range(skip, skip + limit - 1)

        response = query.execute()

        providers = response.data
        total = (
            response.count
            if hasattr(response, "count") and response.count is not None
            else len(providers)
        )

        return providers, total

    except Exception as e:
        print(f"DB Error listing providers: {str(e)}")
        return None, 0  # Return None and 0 count on error


def get_provider_by_id(provider_id: str):
    """
    Fetches a single provider by ID.
    Returns: Tuple (provider_data | None, status_code)
    Status codes: 200 (OK), 404 (Not Found), 500 (Error)
    """
    try:
        response = (
            supabase.table(PROVIDERS_TABLE)
            .select("*")
            .eq("id", provider_id)
            .maybe_single()
            .execute()
        )

        if not response.data:
            return None, 404  # Provider not found

        provider = response.data
        return provider, 200  # Found

    except Exception as e:
        print(f"DB Error fetching provider {provider_id}: {str(e)}")
        return None, 500  # Internal Server Error
