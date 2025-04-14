# --- START OF FILE main.py ---
import math
import os
import uuid
from datetime import datetime
from typing import Any, List, Optional

import uvicorn
from fastapi import Body, Depends, FastAPI, HTTPException, Path, Query, status
# Database imports
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

# Assuming schema.py is in the same directory and contains the Pydantic models
from schema import *

app = FastAPI(title="Cab Management API - SQLite Version")

# --- !!! CHANGE HERE: Database connection setup for SQLite !!! ---
# Use the .db file created previously. Assumes it's in the same directory.
# Use './' to indicate the current directory explicitly.
SQLALCHEMY_DATABASE_URL = "sqlite:///./data.db"

# Add connect_args for SQLite compatibility with multi-threaded access (FastAPI)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
# --- End of CHANGE ---

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()  # Keep for potential future ORM mapping


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        db.execute(text("PRAGMA foreign_keys = ON;"))
        yield db
    finally:
        db.close()


@app.get("/api/partners", response_model=CabPartnerListResponse)
async def list_cab_partners(
    db: Session = Depends(get_db),
    page: int = Query(
        1, ge=1, description="Page number for pagination"
    ),  # Added ge=1 validation
    limit: int = Query(
        10, ge=1, le=100, description="Number of items per page"
    ),  # Added validation
    status: Optional[str] = Query(
        None, description="Filter by partner status (e.g., 'active', 'inactive')"
    ),
    location: Optional[str] = Query(
        None,
        description="Filter by text search in the address field",  # Clarified description
    ),
):
    """
    Retrieves a list of registered cab partners with optional filtering and pagination.
    """
    # --- Base query and params ---
    select_query_base = "SELECT * FROM partners"
    count_query_base = "SELECT COUNT(*) as total FROM partners"
    where_clauses = []
    params = {}

    # --- Apply filters ---
    if status:
        where_clauses.append("status = :status")
        params["status"] = status

    if location:
        # Using LIKE for basic text search in address
        where_clauses.append("address LIKE :location")
        params["location"] = f"%{location}%"

    # --- Construct WHERE part ---
    where_sql = ""
    if where_clauses:
        where_sql = " WHERE " + " AND ".join(where_clauses)

    # --- Count total items for pagination (with filters) ---
    count_query = count_query_base + where_sql
    total_result = db.execute(text(count_query), params)
    total_items = (
        total_result.scalar_one_or_none() or 0
    )  # Use scalar_one_or_none for safety
    total_pages = (total_items + limit - 1) // limit if limit > 0 else 0

    # --- Add pagination to select query ---
    # Ensure offset is not negative
    offset = max(0, (page - 1) * limit)
    select_query = f"{select_query_base}{where_sql} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"  # Added ORDER BY
    params["limit"] = limit
    params["offset"] = offset

    # --- Execute select query ---
    result = db.execute(text(select_query), params)
    # Use .mappings().all() to get dict-like rows easily
    partners_data = result.mappings().all()

    # --- Format response ---
    partners_response_list = []
    for partner_dict in partners_data:
        # Get vehicles for this partner
        vehicles_query = "SELECT * FROM vehicles WHERE partner_id = :partner_id"
        vehicles_result = db.execute(
            text(vehicles_query), {"partner_id": partner_dict["partner_id"]}
        )
        vehicles_data = vehicles_result.mappings().all()

        vehicles_list = [
            Vehicle(
                vehicleId=v["vehicle_id"],
                type=v["type"],
                registration=v["registration"],
                status=v["status"],
                make=v["make"],
                model=v["model"],
                color=v["color"],
            )
            for v in vehicles_data
        ]

        partners_response_list.append(
            CabPartnerResponse(
                partnerId=partner_dict["partner_id"],
                name=partner_dict["name"],
                contact=ContactInfo(
                    phone=partner_dict["phone"], email=partner_dict["email"]
                ),
                address=partner_dict["address"],
                vehicles=vehicles_list,
                status=partner_dict["status"],
                # Convert DB datetime/text to string for JSON compatibility if needed
                createdAt=str(partner_dict["created_at"]),
                updatedAt=str(partner_dict["updated_at"]),
            )
        )

    return {
        "data": partners_response_list,
        "pagination": {
            "currentPage": page,
            "totalPages": total_pages,
            "totalItems": total_items,
            "itemsPerPage": limit,
        },
    }


@app.post(
    "/api/partners", response_model=MessageResponse, status_code=status.HTTP_201_CREATED
)
async def create_cab_partner(partner: CabPartnerCreate, db: Session = Depends(get_db)):
    """
    Registers a new cab partner in the system.
    Generates a unique partner ID.
    """
    # Generate a more unique ID, though collisions are unlikely with short hex
    partner_id = f"partner_{uuid.uuid4().hex[:12]}"  # Slightly longer hex

    # Check for potential conflicts (e.g., email, phone) before inserting
    check_query = """
    SELECT partner_id FROM partners WHERE email = :email OR phone = :phone LIMIT 1
    """
    conflict_check = db.execute(
        text(check_query),
        {"email": partner.contact.email, "phone": partner.contact.phone},
    ).scalar_one_or_none()

    if conflict_check:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A partner with this email or phone number already exists.",
        )

    # Insert partner into database
    query = """
    INSERT INTO partners (partner_id, name, phone, email, address, status, created_at, updated_at)
    VALUES (:partner_id, :name, :phone, :email, :address, :status, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """
    # Note: SQLite triggers will handle future updated_at on UPDATEs

    try:
        db.execute(
            text(query),
            {
                "partner_id": partner_id,
                "name": partner.name,
                "phone": partner.contact.phone,
                "email": partner.contact.email,
                "address": partner.address,
                "status": "active",  # Default status on creation
            },
        )
        db.commit()
    except Exception as e:
        db.rollback()
        # Log the error e
        print(f"Error creating partner: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create partner due to a database error.",
        )

    return {"partnerId": partner_id, "message": "Cab partner created successfully"}


@app.get("/api/partners/{partner_id}", response_model=CabPartnerResponse)
async def get_cab_partner_details(
    partner_id: str = Path(..., description="The ID of the cab partner to retrieve"),
    db: Session = Depends(get_db),
):
    """
    Retrieves detailed information about a specific cab partner, including their vehicles.
    """
    # Get partner details
    query = "SELECT * FROM partners WHERE partner_id = :partner_id"
    result = db.execute(text(query), {"partner_id": partner_id})
    partner = result.mappings().first()  # Use .first() which returns None or a mapping

    if not partner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cab partner with ID {partner_id} not found",
        )

    # Get vehicles for this partner
    vehicles_query = "SELECT * FROM vehicles WHERE partner_id = :partner_id"
    vehicles_result = db.execute(text(vehicles_query), {"partner_id": partner_id})
    vehicles_data = vehicles_result.mappings().all()

    vehicles_list = [
        Vehicle(
            vehicleId=v["vehicle_id"],
            type=v["type"],
            registration=v["registration"],
            status=v["status"],
            make=v["make"],
            model=v["model"],
            color=v["color"],
        )
        for v in vehicles_data
    ]

    return CabPartnerResponse(
        partnerId=partner["partner_id"],
        name=partner["name"],
        contact=ContactInfo(phone=partner["phone"], email=partner["email"]),
        address=partner["address"],
        vehicles=vehicles_list,
        status=partner["status"],
        createdAt=str(partner["created_at"]),
        updatedAt=str(partner["updated_at"]),
    )


@app.put("/api/partners/{partner_id}", response_model=MessageResponse)
async def update_cab_partner(
    update_data: CabPartnerUpdate,
    partner_id: str = Path(..., description="The ID of the cab partner to update"),
    db: Session = Depends(get_db),
):
    """
    Updates information for an existing cab partner.
    Only updates fields that are provided in the request body.
    """
    # Check if partner exists first
    check_query = "SELECT email, phone FROM partners WHERE partner_id = :partner_id"
    check_result = db.execute(text(check_query), {"partner_id": partner_id})
    existing_partner = check_result.mappings().first()

    if not existing_partner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cab partner with ID {partner_id} not found",
        )

    # Build update query dynamically based on provided fields
    update_parts = []
    params = {"partner_id": partner_id}  # Always include the ID for the WHERE clause

    # Check for potential uniqueness conflicts BEFORE updating
    new_email = update_data.contact.get("email") if update_data.contact else None
    new_phone = update_data.contact.get("phone") if update_data.contact else None

    conflict_checks = []
    conflict_params = {"partner_id": partner_id}

    if new_email and new_email != existing_partner["email"]:
        conflict_checks.append("email = :email")
        conflict_params["email"] = new_email
    if new_phone and new_phone != existing_partner["phone"]:
        conflict_checks.append("phone = :phone")
        conflict_params["phone"] = new_phone

    if conflict_checks:
        conflict_query = f"""
        SELECT partner_id FROM partners
        WHERE partner_id != :partner_id AND ({" OR ".join(conflict_checks)})
        LIMIT 1
        """
        conflict_result = db.execute(
            text(conflict_query), conflict_params
        ).scalar_one_or_none()
        if conflict_result:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Update failed: The new email or phone number is already in use by another partner.",
            )

    # Prepare the actual update statement
    if update_data.name is not None:  # Check for None explicitly
        update_parts.append("name = :name")
        params["name"] = update_data.name

    if new_phone:
        update_parts.append("phone = :phone")
        params["phone"] = new_phone

    if new_email:
        update_parts.append("email = :email")
        params["email"] = new_email

    if update_data.address is not None:
        update_parts.append("address = :address")
        params["address"] = update_data.address

    if update_data.status is not None:
        if update_data.status not in ["active", "inactive"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status must be either 'active' or 'inactive'",
            )
        update_parts.append("status = :status")
        params["status"] = update_data.status

    if not update_parts:
        # Return 200 OK but indicate no changes were made
        return {
            "partnerId": partner_id,
            "message": "No update data provided; partner remains unchanged.",
        }

    # Add updated_at manually since SQLite triggers handle it AFTER the update
    # We set it here so the trigger correctly updates it based on THIS transaction time.
    # update_parts.append("updated_at = CURRENT_TIMESTAMP") # Let the trigger handle this

    # Execute update
    try:
        query = (
            # The trigger will update `updated_at`
            f"UPDATE partners SET {', '.join(update_parts)} WHERE partner_id = :partner_id"
        )
        db.execute(text(query), params)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error updating partner {partner_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update partner due to a database error.",
        )

    return {"partnerId": partner_id, "message": "Cab partner updated successfully"}


@app.delete(
    "/api/partners/{partner_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_cab_partner(
    partner_id: str = Path(..., description="The ID of the cab partner to delete"),
    db: Session = Depends(get_db),
):
    """
    Removes a cab partner from the system.
    Associated vehicles, drivers, documents etc. should be deleted automatically
    if CASCADE was set up correctly in the SQLite schema.
    """
    # Check if partner exists before attempting delete
    check_query = "SELECT 1 FROM partners WHERE partner_id = :partner_id LIMIT 1"
    check_result = db.execute(text(check_query), {"partner_id": partner_id})
    if not check_result.scalar_one_or_none():  # Use scalar_one_or_none()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cab partner with ID {partner_id} not found",
        )

    # Delete partner (cascade should handle related records if FKs are ON and defined with CASCADE)
    query = "DELETE FROM partners WHERE partner_id = :partner_id"
    try:
        result = db.execute(text(query), {"partner_id": partner_id})
        db.commit()
        # Optional: Check result.rowcount if needed, though commit implies success if no exception
        if result.rowcount == 0:
            # This case should theoretically be caught by the check above, but double-check
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cab partner with ID {partner_id} not found during delete attempt.",
            )
    except Exception as e:
        db.rollback()
        print(f"Error deleting partner {partner_id}: {e}")
        # Could be a constraint violation if CASCADE isn't working as expected
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete partner due to a database error or constraint issue.",
        )

    return {"partnerId": partner_id, "message": "Cab partner deleted successfully"}


# ==================================
# Vehicle Management Endpoints
# ==================================


@app.post(
    "/api/partners/{partner_id}/vehicles",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_vehicle_to_partner(
    vehicle: VehicleCreate,
    partner_id: str = Path(..., description="The ID of the cab partner"),
    db: Session = Depends(get_db),
):
    """
    Adds a new vehicle to a specific cab partner's fleet.
    Generates a unique vehicle ID.
    """
    # Check if partner exists
    check_query = "SELECT 1 FROM partners WHERE partner_id = :partner_id LIMIT 1"
    if not db.execute(
        text(check_query), {"partner_id": partner_id}
    ).scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cab partner with ID {partner_id} not found",
        )

    # Check if registration is already in use (must be unique across all vehicles)
    reg_query = (
        "SELECT vehicle_id FROM vehicles WHERE registration = :registration LIMIT 1"
    )
    reg_result = db.execute(
        text(reg_query), {"registration": vehicle.registration}
    ).scalar_one_or_none()
    if reg_result:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,  # Use 409 Conflict
            detail=f"Vehicle with registration '{vehicle.registration}' already exists.",
        )

    vehicle_id = f"veh_{uuid.uuid4().hex[:12]}"

    # Insert vehicle
    query = """
    INSERT INTO vehicles
        (vehicle_id, partner_id, type, make, model, color, registration, status, created_at, updated_at)
    VALUES
        (:vehicle_id, :partner_id, :type, :make, :model, :color, :registration, :status, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """
    # Note: SQLite triggers will handle future updated_at on UPDATEs

    try:
        db.execute(
            text(query),
            {
                "vehicle_id": vehicle_id,
                "partner_id": partner_id,
                "type": vehicle.type,
                "make": vehicle.make,
                "model": vehicle.model,
                "color": vehicle.color,
                "registration": vehicle.registration,
                "status": "available",  # Default status
            },
        )
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error adding vehicle for partner {partner_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add vehicle due to a database error.",
        )

    # Include vehicleId in the response message for clarity
    return {
        "partnerId": partner_id,
        "message": f"Vehicle '{vehicle_id}' with registration '{vehicle.registration}' added successfully",
    }


@app.put(
    "/api/partners/{partner_id}/vehicles/{vehicle_id}", response_model=MessageResponse
)
async def update_partner_vehicle(
    update_data: VehicleUpdate,
    partner_id: str = Path(..., description="The ID of the cab partner"),
    vehicle_id: str = Path(..., description="The ID of the vehicle to update"),
    db: Session = Depends(get_db),
):
    """
    Updates information for a specific vehicle within a partner's fleet.
    Only updates fields provided in the request body.
    """
    # Check if vehicle exists AND belongs to the specified partner
    check_query = """
    SELECT registration FROM vehicles
    WHERE vehicle_id = :vehicle_id AND partner_id = :partner_id
    LIMIT 1
    """
    check_result = db.execute(
        text(check_query), {"vehicle_id": vehicle_id, "partner_id": partner_id}
    )
    existing_vehicle = check_result.mappings().first()

    if not existing_vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle with ID {vehicle_id} not found or does not belong to partner {partner_id}",
        )

    # Build update query dynamically
    update_parts = []
    params = {"vehicle_id": vehicle_id}  # Always need vehicle_id for WHERE clause

    # Check for registration conflict BEFORE updating
    if (
        update_data.registration is not None
        and update_data.registration != existing_vehicle["registration"]
    ):
        reg_query = """
        SELECT 1 FROM vehicles
        WHERE registration = :registration AND vehicle_id != :vehicle_id
        LIMIT 1
        """
        reg_result = db.execute(
            text(reg_query),
            {"registration": update_data.registration, "vehicle_id": vehicle_id},
        ).scalar_one_or_none()
        if reg_result:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Update failed: Vehicle with registration '{update_data.registration}' already exists.",
            )
        update_parts.append("registration = :registration")
        params["registration"] = update_data.registration

    # Add other fields to update
    if update_data.type is not None:
        update_parts.append("type = :type")
        params["type"] = update_data.type

    if update_data.status is not None:
        allowed_statuses = ["available", "on_ride", "offline"]
        if update_data.status not in allowed_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Vehicle status must be one of: {', '.join(allowed_statuses)}",
            )
        update_parts.append("status = :status")
        params["status"] = update_data.status

    if update_data.make is not None:
        update_parts.append("make = :make")
        params["make"] = update_data.make

    if update_data.model is not None:
        update_parts.append("model = :model")
        params["model"] = update_data.model

    if update_data.color is not None:
        update_parts.append("color = :color")
        params["color"] = update_data.color

    if not update_parts:
        return {
            "partnerId": partner_id,
            "message": "No update data provided; vehicle remains unchanged.",
        }

    # Execute update - trigger will handle updated_at
    query = (
        f"UPDATE vehicles SET {', '.join(update_parts)} WHERE vehicle_id = :vehicle_id"
    )
    try:
        db.execute(text(query), params)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error updating vehicle {vehicle_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update vehicle due to a database error.",
        )

    return {
        "partnerId": partner_id,
        "message": f"Vehicle {vehicle_id} updated successfully",
    }


@app.delete(
    "/api/partners/{partner_id}/vehicles/{vehicle_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_partner_vehicle(
    partner_id: str = Path(..., description="The ID of the cab partner"),
    vehicle_id: str = Path(..., description="The ID of the vehicle to delete"),
    db: Session = Depends(get_db),
):
    """
    Removes a specific vehicle from a partner's fleet.
    Related records (like documents, locations, driver assignment) should be handled
    by CASCADE or SET NULL based on the SQLite schema definition.
    """
    # Check if vehicle exists and belongs to the partner BEFORE deleting
    check_query = """
    SELECT 1 FROM vehicles
    WHERE vehicle_id = :vehicle_id AND partner_id = :partner_id
    LIMIT 1
    """
    check_result = db.execute(
        text(check_query), {"vehicle_id": vehicle_id, "partner_id": partner_id}
    )

    if not check_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle with ID {vehicle_id} not found or does not belong to partner {partner_id}",
        )

    # Delete vehicle
    query = "DELETE FROM vehicles WHERE vehicle_id = :vehicle_id"
    try:
        result = db.execute(text(query), {"vehicle_id": vehicle_id})
        db.commit()
        if result.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,  # Should have been caught above
                detail=f"Vehicle with ID {vehicle_id} not found during delete attempt.",
            )
    except Exception as e:
        db.rollback()
        print(f"Error deleting vehicle {vehicle_id}: {e}")
        # Check for constraint issues if CASCADE/SET NULL isn't working
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete vehicle due to a database error or constraint issue.",
        )

    return {
        "partnerId": partner_id,
        "message": f"Vehicle {vehicle_id} deleted successfully",
    }


@app.get("/api/partners/{partner_id}/vehicles", response_model=List[Vehicle])
async def list_partner_vehicles(
    partner_id: str = Path(..., description="The ID of the cab partner"),
    db: Session = Depends(get_db),
    status: Optional[str] = Query(
        None, description="Filter vehicles by status (e.g., 'available', 'on_ride')"
    ),
):
    """
    Retrieves all vehicles associated with a specific cab partner, with optional status filtering.
    """
    # Check if partner exists first
    partner_query = "SELECT 1 FROM partners WHERE partner_id = :partner_id LIMIT 1"
    if not db.execute(
        text(partner_query), {"partner_id": partner_id}
    ).scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cab partner with ID {partner_id} not found",
        )

    # Get vehicles, adding status filter if provided
    query = "SELECT * FROM vehicles WHERE partner_id = :partner_id"
    params = {"partner_id": partner_id}

    if status:
        allowed_statuses = ["available", "on_ride", "offline"]
        if status not in allowed_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter. Allowed values: {', '.join(allowed_statuses)}",
            )
        query += " AND status = :status"
        params["status"] = status

    query += " ORDER BY created_at DESC"  # Add ordering

    result = db.execute(text(query), params)
    vehicles_data = result.mappings().all()

    vehicles_list = [
        Vehicle(
            vehicleId=v["vehicle_id"],
            type=v["type"],
            registration=v["registration"],
            status=v["status"],
            make=v["make"],
            model=v["model"],
            color=v["color"],
        )
        for v in vehicles_data
    ]

    return vehicles_list


@app.post(
    "/api/bookings", response_model=BookingResponse, status_code=status.HTTP_201_CREATED
)
async def create_booking(booking: BookingRequest, db: Session = Depends(get_db)):
    """
    Create a new cab booking request.

    This endpoint accepts booking details including pickup and dropoff locations.
    It creates a booking record and initiates the search for available drivers.
    Checks for valid user and payment method. Calculates and stores an estimated fare.
    NOTE: Assumes transaction commit/rollback is handled externally (e.g., by middleware),
    so the 'with db.begin():' block has been removed from this function.
    """
    # Generate a unique booking ID
    booking_id = f"booking_{uuid.uuid4().hex[:12]}"  # Slightly longer ID

    # Verify that the user exists
    user_exists = (
        db.execute(
            text("SELECT 1 FROM users WHERE user_id = :user_id"),
            {"user_id": booking.userId},
        ).scalar()
        is not None
    )

    if not user_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {booking.userId} not found",
        )

    # Verify that the payment method exists and belongs to the user
    payment_method_exists = (
        db.execute(
            text(
                """SELECT 1 FROM payment_methods
                   WHERE payment_method_id = :payment_method_id AND user_id = :user_id"""
            ),
            {"payment_method_id": booking.paymentMethodId, "user_id": booking.userId},
        ).scalar()
        is not None
    )

    if not payment_method_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment method with ID {booking.paymentMethodId} not found or does not belong to user {booking.userId}",
        )

    # --- Fare Calculation Logic ---
    lat1, lon1 = booking.pickupLocation.latitude, booking.pickupLocation.longitude
    lat2, lon2 = booking.dropoffLocation.latitude, booking.dropoffLocation.longitude

    # Haversine formula for distance
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance_km = R * c  # Distance in km

    # Simple fare components
    base_fare = 50.0
    distance_charge_per_km = 12.0
    time_charge_per_min = 1.5
    estimated_duration_min = int(distance_km * 2.5)  # Rough estimate

    distance_charge = distance_km * distance_charge_per_km
    time_charge = estimated_duration_min * time_charge_per_min
    surge_multiplier = 1.0
    tax_rate = 0.05

    subtotal = base_fare + distance_charge + time_charge
    estimated_fare_before_tax = subtotal * surge_multiplier
    tax_amount = estimated_fare_before_tax * tax_rate
    estimated_fare_total = estimated_fare_before_tax + tax_amount
    currency = "INR"

    # Perform database operations within the existing transaction scope
    try:
        # Insert the booking record
        db.execute(
            text("""
                INSERT INTO bookings (
                    booking_id, user_id, status,
                    pickup_latitude, pickup_longitude, pickup_address,
                    dropoff_latitude, dropoff_longitude, dropoff_address,
                    vehicle_type, payment_method_id, estimated_fare_amount,
                    estimated_fare_currency, estimated_distance, estimated_duration
                ) VALUES (
                    :booking_id, :user_id, :status,
                    :pickup_latitude, :pickup_longitude, :pickup_address,
                    :dropoff_latitude, :dropoff_longitude, :dropoff_address,
                    :vehicle_type, :payment_method_id, :estimated_fare_amount,
                    :estimated_fare_currency, :estimated_distance, :estimated_duration
                )
            """),
            {
                "booking_id": booking_id,
                "user_id": booking.userId,
                "status": BookingStatus.SEARCHING,
                "pickup_latitude": booking.pickupLocation.latitude,
                "pickup_longitude": booking.pickupLocation.longitude,
                "pickup_address": booking.pickupLocation.address,
                "dropoff_latitude": booking.dropoffLocation.latitude,
                "dropoff_longitude": booking.dropoffLocation.longitude,
                "dropoff_address": booking.dropoffLocation.address,
                "vehicle_type": booking.vehicleType,
                "payment_method_id": booking.paymentMethodId,
                "estimated_fare_amount": round(estimated_fare_total, 2),
                "estimated_fare_currency": currency,
                "estimated_distance": round(distance_km, 2),
                "estimated_duration": estimated_duration_min,
            },
        )

        # Insert initial status in booking history
        db.execute(
            text("""
                INSERT INTO booking_status_history (booking_id, status)
                VALUES (:booking_id, :status)
            """),
            {"booking_id": booking_id, "status": BookingStatus.SEARCHING},
        )

        # Insert fare calculation record
        db.execute(
            text("""
                INSERT INTO fare_calculations (
                    booking_id, base_fare, distance_charge, time_charge,
                    surge_multiplier, tax_amount, total_amount, currency
                ) VALUES (
                    :booking_id, :base_fare, :distance_charge, :time_charge,
                    :surge_multiplier, :tax_amount, :total_amount, :currency
                )
            """),
            {
                "booking_id": booking_id,
                "base_fare": round(base_fare, 2),
                "distance_charge": round(distance_charge, 2),
                "time_charge": round(time_charge, 2),
                "surge_multiplier": surge_multiplier,
                "tax_amount": round(tax_amount, 2),
                "total_amount": round(estimated_fare_total, 2),
                "currency": currency,
            },
        )

        # db.commit() is expected to be called externally after the request finishes successfully
        # db.rollback() is expected to be called externally if an exception occurs

    except Exception as e:
        # If an error occurs during DB operations, the external handler should ideally rollback.
        # Re-raising the exception ensures the external handler knows about the failure.
        # Log the error here if desired.
        # logger.error(f"Database error during booking creation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while creating the booking: {e}",
        ) from e

    # In a real implementation, background tasks would start searching for drivers here.

    return BookingResponse(
        bookingId=booking_id,
        status=BookingStatus.SEARCHING,
        estimatedFare=FareInfo(
            currency=currency,
            amount=round(estimated_fare_total, 2),
            breakdown={
                "baseFare": round(base_fare, 2),
                "distanceCharge": round(distance_charge, 2),
                "timeCharge": round(time_charge, 2),
                "surgeMultiplier": surge_multiplier,
                "tax": round(tax_amount, 2),
            },
        ),
        message="Searching for nearby drivers...",
    )


def parse_datetime(dt_value):
    if isinstance(dt_value, datetime):
        return dt_value
    elif isinstance(dt_value, str):
        # Handle potential 'Z' suffix and spaces instead of 'T'
        dt_str = dt_value.replace("Z", "+00:00").replace(" ", "T")
        try:
            # Attempt parsing, potentially handling microseconds if present
            return datetime.fromisoformat(dt_str)
        except ValueError:
            # Log or handle parsing errors if necessary
            print(f"Warning: Could not parse datetime string: {dt_value}")
            return None  # Or raise an error, or return original string
    return None


@app.get("/api/bookings/{booking_id}", response_model=BookingDetail)
async def get_booking_details(
    booking_id: str = Path(..., description="The ID of the booking to retrieve"),
    db: Session = Depends(get_db),
):
    """
    Retrieve details of a specific booking.

    This endpoint returns the current status and all available details of a booking,
    including driver and vehicle information if assigned, and fare breakdown.
    """
    # Fetch booking details along with fare calculation components
    booking_result = db.execute(
        text("""
            SELECT
                b.*,
                fc.base_fare, fc.distance_charge, fc.time_charge,
                fc.surge_multiplier, fc.tax_amount, fc.other_charges,
                fc.total_amount AS calculated_total, fc.currency AS calculated_currency
            FROM bookings b
            LEFT JOIN fare_calculations fc ON b.booking_id = fc.booking_id
            WHERE b.booking_id = :booking_id
        """),
        {"booking_id": booking_id},
    ).fetchone()

    if not booking_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking with ID {booking_id} not found",
        )

    # Convert row to dictionary using ._mapping for reliability
    # booking_data = dict(booking_result) <-- This caused the ValueError
    if hasattr(booking_result, "_mapping"):
        booking_data = dict(booking_result._mapping)
    else:
        # Fallback or raise error if _mapping is not available (should be for standard drivers)
        raise TypeError(
            "SQLAlchemy result object does not have a '_mapping' attribute."
        )

    # Fetch driver details if assigned
    driver_info = None
    if booking_data.get("driver_id"):  # Use .get for safer access
        driver_result = db.execute(
            text("""
                SELECT driver_id, first_name, last_name, phone, average_rating
                FROM drivers
                WHERE driver_id = :driver_id
            """),
            {"driver_id": booking_data["driver_id"]},
        ).fetchone()
        if driver_result:
            # Convert driver row to dictionary
            if hasattr(driver_result, "_mapping"):
                driver_dict = dict(driver_result._mapping)
                driver_info = DriverInfo(
                    driverId=driver_dict.get("driver_id"),
                    name=f"{driver_dict.get('first_name', '')} {driver_dict.get('last_name', '')}".strip(),
                    phone=driver_dict.get("phone"),
                    # Handle potential None rating from DB
                    rating=float(driver_dict.get("average_rating", 0.0) or 0.0),
                )
            else:
                print("Warning: Could not convert driver result to dict.")

    # Fetch vehicle details if assigned
    vehicle_info = None
    if booking_data.get("vehicle_id"):
        vehicle_result = db.execute(
            text("""
                SELECT vehicle_id, make, model, color, registration
                FROM vehicles
                WHERE vehicle_id = :vehicle_id
            """),
            {"vehicle_id": booking_data["vehicle_id"]},
        ).fetchone()
        if vehicle_result:
            # Convert vehicle row to dictionary
            if hasattr(vehicle_result, "_mapping"):
                vehicle_dict = dict(vehicle_result._mapping)
                vehicle_info = VehicleInfo(
                    vehicleId=vehicle_dict.get("vehicle_id"),
                    make=vehicle_dict.get("make"),
                    model=vehicle_dict.get("model"),
                    color=vehicle_dict.get("color"),
                    registration=vehicle_dict.get("registration"),
                )
            else:
                print("Warning: Could not convert vehicle result to dict.")

    # Prepare estimated fare details
    estimated_fare = None
    if booking_data.get("estimated_fare_amount") is not None:
        breakdown = None
        # Check if fare calculation details were fetched and are not None
        if booking_data.get("base_fare") is not None:
            breakdown_components = {
                "baseFare": booking_data.get("base_fare"),
                "distanceCharge": booking_data.get("distance_charge"),
                "timeCharge": booking_data.get("time_charge"),
                "surgeMultiplier": booking_data.get("surge_multiplier"),
                "tax": booking_data.get("tax_amount"),
                "otherCharges": booking_data.get("other_charges"),
            }
            # Filter out None values from breakdown components
            breakdown = {k: v for k, v in breakdown_components.items() if v is not None}

        estimated_fare = FareInfo(
            currency=booking_data.get(
                "estimated_fare_currency", "INR"
            ),  # Default currency
            amount=float(booking_data["estimated_fare_amount"]),
            breakdown=breakdown if breakdown else None,
        )

    # Prepare actual fare details
    actual_fare = None
    if booking_data.get("actual_fare_amount") is not None:
        actual_fare = FareInfo(
            currency=booking_data.get(
                "actual_fare_currency", "INR"
            ),  # Default currency
            amount=float(booking_data["actual_fare_amount"]),
            # Actual fare typically doesn't include breakdown in summary
        )

    # Calculate simple ETA placeholder for active bookings
    eta = None
    current_status = booking_data.get("status")
    if current_status in [BookingStatus.CONFIRMED, BookingStatus.DRIVER_ARRIVED]:
        # Use estimated_duration as a proxy, or a fixed value
        eta = booking_data.get(
            "estimated_duration"
        )  # Maybe divide by 2? Depends on meaning
        if eta is None:
            eta = 5  # Fallback static ETA

    # Construct the final response object using the Pydantic model
    # This ensures validation against the BookingDetail schema
    try:
        response_payload = BookingDetail(
            bookingId=booking_data.get("booking_id"),
            userId=booking_data.get("user_id"),
            status=current_status,  # Use already fetched status
            pickupLocation=Location(
                latitude=float(booking_data.get("pickup_latitude", 0.0)),
                longitude=float(booking_data.get("pickup_longitude", 0.0)),
                address=booking_data.get("pickup_address"),
            ),
            dropoffLocation=Location(
                latitude=float(booking_data.get("dropoff_latitude", 0.0)),
                longitude=float(booking_data.get("dropoff_longitude", 0.0)),
                address=booking_data.get("dropoff_address"),
            ),
            vehicleType=booking_data.get("vehicle_type"),
            createdAt=str(booking_data.get("created_at")),
            updatedAt=str(booking_data.get("updated_at")),
            estimatedFare=estimated_fare,
            actualFare=actual_fare,
            driverInfo=driver_info,
            vehicleInfo=vehicle_info,
            eta=eta,
        )
    except Exception as e:
        # Catch potential validation errors during Pydantic model creation
        print(f"Error creating BookingDetail response model: {e}")
        print(f"Data passed to model: {booking_data}")  # Log the data for debugging
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing booking data: {e}",
        )

    return response_payload


@app.post("/api/bookings/{booking_id}/cancel", response_model=CancelBookingResponse)
@app.post("/api/bookings/{booking_id}/cancel", response_model=CancelBookingResponse)
async def cancel_booking(
    booking_id: str = Path(..., description="The ID of the booking to cancel"),
    cancel_request: Optional[CancelBookingRequest] = Body(
        None, description="Optional reason for cancellation"
    ),
    db: Session = Depends(get_db),
):
    """
    Cancel an existing booking.

    Allows cancellation if the booking is not already completed or cancelled.
    Applies a cancellation fee based on the booking status at the time of cancellation
    (e.g., if CONFIRMED or DRIVER_ARRIVED). Updates driver/vehicle status if assigned.
    NOTE: Assumes transaction commit/rollback is handled externally.
    """
    cancellation_fee = None
    message = "Booking cancelled successfully."

    # Fetch current booking details
    booking_result = db.execute(
        text("SELECT * FROM bookings WHERE booking_id = :booking_id"),
        {"booking_id": booking_id},
    ).fetchone()

    if not booking_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking with ID {booking_id} not found",
        )

    # Convert row to dictionary using ._mapping
    if hasattr(booking_result, "_mapping"):
        booking_data = dict(booking_result._mapping)
    else:
        # Fallback or raise error if _mapping is not available
        raise TypeError(
            "SQLAlchemy result object does not have a '_mapping' attribute."
        )

    current_status = booking_data.get("status")

    # Check if booking can be cancelled
    # Compare against Enum values if current_status is a string from DB
    if current_status in [BookingStatus.COMPLETED.value, BookingStatus.CANCELLED.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel a booking with status: {current_status}",
        )

    # --- Database Operations (within external transaction scope) ---
    try:
        # Determine if cancellation fee applies (example logic)
        fee_amount = 0.0
        fee_currency = "INR"  # Default or fetch from booking if available
        # Check against Enum members for clarity
        if current_status and BookingStatus(current_status) in [
            BookingStatus.CONFIRMED,
            BookingStatus.DRIVER_ARRIVED,
        ]:
            # Example fee logic: Apply a fixed fee
            fee_amount = 50.00
            cancellation_fee = FareInfo(currency=fee_currency, amount=fee_amount)
            message += f" A cancellation fee of {fee_amount} {fee_currency} may apply."
            # Update booking record with the fee amount
            db.execute(
                text("""
                    UPDATE bookings
                    SET cancellation_fee_amount = :fee_amount
                    WHERE booking_id = :booking_id
                """),
                {"fee_amount": fee_amount, "booking_id": booking_id},
            )

        # Update booking status to CANCELLED
        db.execute(
            text("""
                UPDATE bookings
                SET status = :status,
                    cancellation_reason = :reason
                    -- Assuming trigger handles updated_at
                WHERE booking_id = :booking_id
            """),
            {
                "status": BookingStatus.CANCELLED.value,  # Use Enum value
                "reason": cancel_request.reason if cancel_request else None,
                "booking_id": booking_id,
            },
        )

        # Add entry to booking status history
        db.execute(
            text("""
                INSERT INTO booking_status_history (booking_id, status)
                VALUES (:booking_id, :status)
            """),
            # Use Enum value here as well
            {"booking_id": booking_id, "status": BookingStatus.CANCELLED.value},
        )

        # If the booking had an assigned driver, make them available again
        driver_id = booking_data.get("driver_id")
        if driver_id:
            # Consider checking current driver status before updating
            db.execute(
                text("""
                    UPDATE drivers
                    SET status = 'available' -- Or appropriate status based on your logic
                    WHERE driver_id = :driver_id AND status = 'on_ride' -- Example condition
                """),
                {"driver_id": driver_id},
            )

        # If the booking had an assigned vehicle, make it available again
        vehicle_id = booking_data.get("vehicle_id")
        if vehicle_id:
            # Consider checking current vehicle status
            db.execute(
                text("""
                    UPDATE vehicles
                    SET status = 'available' -- Or appropriate status
                    WHERE vehicle_id = :vehicle_id AND status = 'on_ride' -- Example condition
                """),
                {"vehicle_id": vehicle_id},
            )

        # Commit is expected to be handled externally

    except Exception as e:
        # If an error occurs, the external handler should rollback.
        # Re-raise the exception for the external handler.
        # You might want to log the error here.
        # logger.error(f"Database error during booking cancellation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while cancelling the booking: {e}",
        ) from e

    return CancelBookingResponse(
        bookingId=booking_id,
        status=BookingStatus.CANCELLED,  # Return the Enum member directly
        message=message,
        cancellationFee=cancellation_fee,
    )


@app.put("/api/bookings/{booking_id}/destination", response_model=BookingDetail)
@app.put("/api/bookings/{booking_id}/destination", response_model=BookingDetail)
async def update_destination(
    booking_id: str = Path(..., description="The ID of the booking to update"),
    new_location: Location = Body(..., description="The new dropoff location details"),
    db: Session = Depends(get_db),
):
    """
    Update the destination for an ongoing or confirmed booking.

    Allows changing the dropoff location while a ride is confirmed or in progress.
    Recalculates the estimated fare based on the original pickup and the new destination.
    Updates the booking record and the associated fare calculation record.
    Returns the full updated booking details.
    NOTE: Assumes transaction commit/rollback is handled externally.
    """
    # Fetch current booking details
    booking_result = db.execute(
        text("SELECT * FROM bookings WHERE booking_id = :booking_id"),
        {"booking_id": booking_id},
    ).fetchone()

    if not booking_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking with ID {booking_id} not found",
        )

    # Convert row to dictionary using ._mapping
    if hasattr(booking_result, "_mapping"):
        booking_data = dict(booking_result._mapping)
    else:
        raise TypeError(
            "SQLAlchemy result object does not have a '_mapping' attribute."
        )

    current_status = booking_data.get("status")

    # Check if the booking state allows destination update
    allowed_statuses = [
        BookingStatus.CONFIRMED.value,
        BookingStatus.DRIVER_ARRIVED.value,
        BookingStatus.ONGOING.value,
    ]
    if current_status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Destination can only be updated when status is one of: {', '.join([s.split('.')[-1] for s in allowed_statuses])}",  # Show enum names
        )

    # --- Recalculate Estimated Fare based on NEW Destination ---
    lat1 = booking_data.get("pickup_latitude")
    lon1 = booking_data.get("pickup_longitude")
    lat2 = new_location.latitude
    lon2 = new_location.longitude

    # Ensure we have valid coordinates
    if lat1 is None or lon1 is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Booking is missing pickup location coordinates.",
        )

    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    new_distance_km = R * c

    # Use simple fare logic (same as create_booking for consistency)
    # Fetch original components if needed for more complex logic
    base_fare = 50.0  # Example: fetch from original fare_calculations if needed
    distance_charge_per_km = 12.0
    time_charge_per_min = 1.5
    new_estimated_duration_min = int(new_distance_km * 2.5)

    new_distance_charge = new_distance_km * distance_charge_per_km
    new_time_charge = new_estimated_duration_min * time_charge_per_min
    surge_multiplier = 1.0  # Fetch from original fare_calc if needed
    tax_rate = 0.05  # Fetch from original fare_calc if needed

    new_subtotal = base_fare + new_distance_charge + new_time_charge
    new_estimated_fare_before_tax = new_subtotal * surge_multiplier
    new_tax_amount = new_estimated_fare_before_tax * tax_rate
    new_estimated_fare_total = new_estimated_fare_before_tax + new_tax_amount
    currency = booking_data.get(
        "estimated_fare_currency", "INR"
    )  # Use original currency

    # --- Database Operations (within external transaction scope) ---
    try:
        # Update the bookings table
        db.execute(
            text("""
                UPDATE bookings
                SET dropoff_latitude = :latitude,
                    dropoff_longitude = :longitude,
                    dropoff_address = :address,
                    estimated_fare_amount = :fare_amount,
                    estimated_distance = :distance,
                    estimated_duration = :duration
                    -- Assuming trigger handles updated_at
                WHERE booking_id = :booking_id
            """),
            {
                "latitude": new_location.latitude,
                "longitude": new_location.longitude,
                "address": new_location.address,
                "fare_amount": round(new_estimated_fare_total, 2),
                "distance": round(new_distance_km, 2),
                "duration": new_estimated_duration_min,
                "booking_id": booking_id,
            },
        )

        # Update the corresponding fare_calculations record
        # Consider if this update should only happen if a fare_calculation record exists
        update_fare_calc_sql = text("""
            UPDATE fare_calculations
            SET base_fare = :base_fare,
                distance_charge = :distance_charge,
                time_charge = :time_charge,
                tax_amount = :tax_amount,
                total_amount = :total_amount
                -- Consider updating other fields like surge_multiplier if logic dictates
            WHERE booking_id = :booking_id
        """)
        db.execute(
            update_fare_calc_sql,
            {
                "booking_id": booking_id,
                "base_fare": round(base_fare, 2),
                "distance_charge": round(new_distance_charge, 2),
                "time_charge": round(new_time_charge, 2),
                "tax_amount": round(new_tax_amount, 2),
                "total_amount": round(new_estimated_fare_total, 2),
            },
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while updating the destination: {e}",
        ) from e

    updated_booking_details = await get_booking_details(booking_id=booking_id, db=db)
    return updated_booking_details


if __name__ == "__main__":
    print("--- Starting FastAPI Application with SQLite Backend ---")
    print(f"--- Database URL: {SQLALCHEMY_DATABASE_URL} ---")

    db_file = SQLALCHEMY_DATABASE_URL.split("///./")[-1]
    if not os.path.exists(db_file):
        print(f"\nWARNING: Database file '{db_file}' not found.")
        print("Please ensure you have created it using the SQLite schema script:")
        print(f"  sqlite3 {db_file} < schema.sqlite.sql\n")
    else:
        print(f"--- Found database file: {db_file} ---")

    # Run the FastAPI application using Uvicorn
    uvicorn.run(
        "main:app",  # Points to the 'app' instance in the 'main.py' file
        host="0.0.0.0",  # Listen on all available network interfaces
        port=8000,  # Standard port for development
        reload=True,  # Enable auto-reload for development convenience
    )
