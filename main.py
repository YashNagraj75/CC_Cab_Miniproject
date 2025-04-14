# --- START OF FILE main.py ---
import os
import uuid
from datetime import datetime
from typing import List, Optional

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Path, Query, status
# Database imports
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

# Assuming schema.py is in the same directory and contains the Pydantic models
from schema import (CabPartnerCreate, CabPartnerListResponse,
                    CabPartnerResponse, CabPartnerUpdate, ContactInfo,
                    MessageResponse, Vehicle, VehicleCreate, VehicleUpdate)

app = FastAPI(title="Cab Partner Management API - SQLite Version")

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


# API endpoints with database interaction
# NOTE: The raw SQL queries used below are generally compatible between MySQL and SQLite
# for the operations performed (basic CRUD, filtering, pagination).
# The main differences (ENUMs, ON UPDATE CURRENT_TIMESTAMP, AUTO_INCREMENT) were
# handled during the schema conversion to the .db file (using TEXT+CHECK, Triggers, INTEGER PRIMARY KEY).


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


# --- Main execution block ---
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
