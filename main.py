import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Path, Query, status
from pydantic import BaseModel, EmailStr, Field

# Database imports
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

app = FastAPI(title="Cab Partner Management API")

# Database connection setup
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://username:password@localhost/cab_management"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic models (same as before)
class ContactInfo(BaseModel):
    phone: str
    email: EmailStr


class Vehicle(BaseModel):
    vehicleId: str
    type: str
    registration: str
    status: str = "available"
    make: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None


class VehicleCreate(BaseModel):
    type: str
    registration: str
    make: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None


class VehicleUpdate(BaseModel):
    type: Optional[str] = None
    registration: Optional[str] = None
    status: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None


class CabPartnerBase(BaseModel):
    name: str
    contact: ContactInfo
    address: Optional[str] = None


class CabPartnerCreate(CabPartnerBase):
    pass


class CabPartnerUpdate(BaseModel):
    name: Optional[str] = None
    contact: Optional[Dict[str, str]] = None
    address: Optional[str] = None
    status: Optional[str] = None


class CabPartnerResponse(BaseModel):
    partnerId: str
    name: str
    contact: ContactInfo
    address: Optional[str] = None
    vehicles: List[Vehicle] = []
    status: str
    createdAt: datetime
    updatedAt: datetime


class CabPartnerListResponse(BaseModel):
    data: List[CabPartnerResponse]
    pagination: Dict[str, int]


class MessageResponse(BaseModel):
    partnerId: str
    message: str


# API endpoints with database interaction
@app.get("/api/partners", response_model=CabPartnerListResponse)
async def list_cab_partners(
    db: Session = Depends(get_db),
    page: int = Query(1, description="Page number for pagination"),
    limit: int = Query(10, description="Number of items per page"),
    status: Optional[str] = Query(
        None, description="Filter by partner status (e.g., 'active', 'inactive')"
    ),
    location: Optional[str] = Query(
        None, description="Filter by general location or service area"
    ),
):
    """
    Retrieves a list of registered cab partners with optional filtering.
    """
    # Base query
    query = "SELECT * FROM partners WHERE 1=1"
    params = {}

    # Apply filters
    if status:
        query += " AND status = :status"
        params["status"] = status

    if location:
        query += " AND address LIKE :location"
        params["location"] = f"%{location}%"

    # Add pagination
    query += " LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = (page - 1) * limit

    # Execute query
    result = db.execute(text(query), params)
    partners_data = result.fetchall()

    # Count total items for pagination
    count_query = "SELECT COUNT(*) as total FROM partners WHERE 1=1"
    count_params = {}

    if status:
        count_query += " AND status = :status"
        count_params["status"] = status

    if location:
        count_query += " AND address LIKE :location"
        count_params["location"] = f"%{location}%"

    total_result = db.execute(text(count_query), count_params)
    total_items = total_result.fetchone()[0]
    total_pages = (total_items + limit - 1) // limit

    # Format response
    partners = []
    for partner in partners_data:
        # Get vehicles for this partner
        vehicles_query = "SELECT * FROM vehicles WHERE partner_id = :partner_id"
        vehicles_result = db.execute(
            text(vehicles_query), {"partner_id": partner.partner_id}
        )
        vehicles_data = vehicles_result.fetchall()

        vehicles = []
        for vehicle in vehicles_data:
            vehicles.append(
                Vehicle(
                    vehicleId=vehicle.vehicle_id,
                    type=vehicle.type,
                    registration=vehicle.registration,
                    status=vehicle.status,
                    make=vehicle.make,
                    model=vehicle.model,
                    color=vehicle.color,
                )
            )

        partners.append(
            CabPartnerResponse(
                partnerId=partner.partner_id,
                name=partner.name,
                contact=ContactInfo(phone=partner.phone, email=partner.email),
                address=partner.address,
                vehicles=vehicles,
                status=partner.status,
                createdAt=partner.created_at,
                updatedAt=partner.updated_at,
            )
        )

    return {
        "data": partners,
        "pagination": {
            "currentPage": page,
            "totalPages": total_pages,
            "totalItems": total_items,
        },
    }


@app.post(
    "/api/partners", response_model=MessageResponse, status_code=status.HTTP_201_CREATED
)
async def create_cab_partner(partner: CabPartnerCreate, db: Session = Depends(get_db)):
    """
    Registers a new cab partner in the system.
    """
    partner_id = f"partner{uuid.uuid4().hex[:6]}"

    # Insert partner into database
    query = """
    INSERT INTO partners (partner_id, name, phone, email, address)
    VALUES (:partner_id, :name, :phone, :email, :address)
    """

    db.execute(
        text(query),
        {
            "partner_id": partner_id,
            "name": partner.name,
            "phone": partner.contact.phone,
            "email": partner.contact.email,
            "address": partner.address,
        },
    )

    db.commit()

    return {"partnerId": partner_id, "message": "Cab partner created successfully"}


@app.get("/api/partners/{partner_id}", response_model=CabPartnerResponse)
async def get_cab_partner_details(
    partner_id: str = Path(..., description="The ID of the cab partner to retrieve"),
    db: Session = Depends(get_db),
):
    """
    Retrieves detailed information about a specific cab partner.
    """
    # Get partner details
    query = "SELECT * FROM partners WHERE partner_id = :partner_id"
    result = db.execute(text(query), {"partner_id": partner_id})
    partner = result.fetchone()

    if not partner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cab partner with ID {partner_id} not found",
        )

    # Get vehicles for this partner
    vehicles_query = "SELECT * FROM vehicles WHERE partner_id = :partner_id"
    vehicles_result = db.execute(text(vehicles_query), {"partner_id": partner_id})
    vehicles_data = vehicles_result.fetchall()

    vehicles = []
    for vehicle in vehicles_data:
        vehicles.append(
            Vehicle(
                vehicleId=vehicle.vehicle_id,
                type=vehicle.type,
                registration=vehicle.registration,
                status=vehicle.status,
                make=vehicle.make,
                model=vehicle.model,
                color=vehicle.color,
            )
        )

    return CabPartnerResponse(
        partnerId=partner.partner_id,
        name=partner.name,
        contact=ContactInfo(phone=partner.phone, email=partner.email),
        address=partner.address,
        vehicles=vehicles,
        status=partner.status,
        createdAt=partner.created_at,
        updatedAt=partner.updated_at,
    )


@app.put("/api/partners/{partner_id}", response_model=MessageResponse)
async def update_cab_partner(
    update_data: CabPartnerUpdate,
    partner_id: str = Path(..., description="The ID of the cab partner to update"),
    db: Session = Depends(get_db),
):
    """
    Updates information for an existing cab partner.
    """
    # Check if partner exists
    check_query = "SELECT 1 FROM partners WHERE partner_id = :partner_id"
    check_result = db.execute(text(check_query), {"partner_id": partner_id})
    if not check_result.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cab partner with ID {partner_id} not found",
        )

    # Build update query dynamically based on provided fields
    update_parts = []
    params = {"partner_id": partner_id}

    if update_data.name:
        update_parts.append("name = :name")
        params["name"] = update_data.name

    if update_data.contact and "phone" in update_data.contact:
        update_parts.append("phone = :phone")
        params["phone"] = update_data.contact["phone"]

    if update_data.contact and "email" in update_data.contact:
        update_parts.append("email = :email")
        params["email"] = update_data.contact["email"]

    if update_data.address:
        update_parts.append("address = :address")
        params["address"] = update_data.address

    if update_data.status:
        if update_data.status not in ["active", "inactive"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status must be either 'active' or 'inactive'",
            )
        update_parts.append("status = :status")
        params["status"] = update_data.status

    if not update_parts:
        return {"partnerId": partner_id, "message": "No updates provided"}

    # Execute update
    query = (
        f"UPDATE partners SET {', '.join(update_parts)} WHERE partner_id = :partner_id"
    )
    db.execute(text(query), params)
    db.commit()

    return {"partnerId": partner_id, "message": "Cab partner updated successfully"}


@app.delete("/api/partners/{partner_id}", response_model=MessageResponse)
async def delete_cab_partner(
    partner_id: str = Path(..., description="The ID of the cab partner to delete"),
    db: Session = Depends(get_db),
):
    """
    Removes a cab partner from the system.
    """
    # Check if partner exists
    check_query = "SELECT 1 FROM partners WHERE partner_id = :partner_id"
    check_result = db.execute(text(check_query), {"partner_id": partner_id})
    if not check_result.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cab partner with ID {partner_id} not found",
        )

    # Delete partner (cascade will handle related records)
    query = "DELETE FROM partners WHERE partner_id = :partner_id"
    db.execute(text(query), {"partner_id": partner_id})
    db.commit()

    return {"partnerId": partner_id, "message": "Cab partner deleted successfully"}


# Vehicle Management Endpoints
@app.post("/api/partners/{partner_id}/vehicles", response_model=MessageResponse)
async def add_vehicle_to_partner(
    vehicle: VehicleCreate,
    partner_id: str = Path(..., description="The ID of the cab partner"),
    db: Session = Depends(get_db),
):
    """
    Adds a new vehicle to a cab partner's fleet.
    """
    # Check if partner exists
    check_query = "SELECT 1 FROM partners WHERE partner_id = :partner_id"
    check_result = db.execute(text(check_query), {"partner_id": partner_id})
    if not check_result.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cab partner with ID {partner_id} not found",
        )

    # Check if registration is already in use
    reg_query = "SELECT 1 FROM vehicles WHERE registration = :registration"
    reg_result = db.execute(text(reg_query), {"registration": vehicle.registration})
    if reg_result.fetchone():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Vehicle with registration {vehicle.registration} already exists",
        )

    vehicle_id = f"veh{uuid.uuid4().hex[:6]}"

    # Insert vehicle
    query = """
    INSERT INTO vehicles (vehicle_id, partner_id, type, make, model, color, registration)
    VALUES (:vehicle_id, :partner_id, :type, :make, :model, :color, :registration)
    """

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
        },
    )

    db.commit()

    return {
        "partnerId": partner_id,
        "message": f"Vehicle {vehicle_id} added successfully",
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
    Updates information for a specific vehicle in a partner's fleet.
    """
    # Check if vehicle exists and belongs to the partner
    check_query = """
    SELECT 1 FROM vehicles 
    WHERE vehicle_id = :vehicle_id AND partner_id = :partner_id
    """
    check_result = db.execute(
        text(check_query), {"vehicle_id": vehicle_id, "partner_id": partner_id}
    )

    if not check_result.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle with ID {vehicle_id} not found for this partner",
        )

    # Build update query dynamically
    update_parts = []
    params = {"vehicle_id": vehicle_id}

    if update_data.type:
        update_parts.append("type = :type")
        params["type"] = update_data.type

    if update_data.registration:
        # Check if new registration conflicts with existing one
        if update_data.registration:
            reg_query = """
            SELECT 1 FROM vehicles 
            WHERE registration = :registration AND vehicle_id != :vehicle_id
            """
            reg_result = db.execute(
                text(reg_query),
                {"registration": update_data.registration, "vehicle_id": vehicle_id},
            )
            if reg_result.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Vehicle with registration {update_data.registration} already exists",
                )

        update_parts.append("registration = :registration")
        params["registration"] = update_data.registration

    if update_data.status:
        if update_data.status not in ["available", "on_ride", "offline"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vehicle status must be one of: available, on_ride, offline",
            )
        update_parts.append("status = :status")
        params["status"] = update_data.status

    if update_data.make:
        update_parts.append("make = :make")
        params["make"] = update_data.make

    if update_data.model:
        update_parts.append("model = :model")
        params["model"] = update_data.model

    if update_data.color:
        update_parts.append("color = :color")
        params["color"] = update_data.color

    if not update_parts:
        return {"partnerId": partner_id, "message": "No updates provided"}

    # Execute update
    query = (
        f"UPDATE vehicles SET {', '.join(update_parts)} WHERE vehicle_id = :vehicle_id"
    )
    db.execute(text(query), params)
    db.commit()

    return {
        "partnerId": partner_id,
        "message": f"Vehicle {vehicle_id} updated successfully",
    }


@app.delete(
    "/api/partners/{partner_id}/vehicles/{vehicle_id}", response_model=MessageResponse
)
async def delete_partner_vehicle(
    partner_id: str = Path(..., description="The ID of the cab partner"),
    vehicle_id: str = Path(..., description="The ID of the vehicle to delete"),
    db: Session = Depends(get_db),
):
    """
    Removes a vehicle from a partner's fleet.
    """
    # Check if vehicle exists and belongs to the partner
    check_query = """
    SELECT 1 FROM vehicles 
    WHERE vehicle_id = :vehicle_id AND partner_id = :partner_id
    """
    check_result = db.execute(
        text(check_query), {"vehicle_id": vehicle_id, "partner_id": partner_id}
    )

    if not check_result.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vehicle with ID {vehicle_id} not found for this partner",
        )

    # Delete vehicle
    query = "DELETE FROM vehicles WHERE vehicle_id = :vehicle_id"
    db.execute(text(query), {"vehicle_id": vehicle_id})
    db.commit()

    return {
        "partnerId": partner_id,
        "message": f"Vehicle {vehicle_id} deleted successfully",
    }


@app.get("/api/partners/{partner_id}/vehicles", response_model=List[Vehicle])
async def list_partner_vehicles(
    partner_id: str = Path(..., description="The ID of the cab partner"),
    db: Session = Depends(get_db),
):
    """
    Retrieves all vehicles associated with a specific cab partner.
    """
    # Check if partner exists
    partner_query = "SELECT 1 FROM partners WHERE partner_id = :partner_id"
    partner_result = db.execute(text(partner_query), {"partner_id": partner_id})
    if not partner_result.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cab partner with ID {partner_id} not found",
        )

    # Get vehicles
    query = "SELECT * FROM vehicles WHERE partner_id = :partner_id"
    result = db.execute(text(query), {"partner_id": partner_id})
    vehicles_data = result.fetchall()

    vehicles = []
    for vehicle in vehicles_data:
        vehicles.append(
            Vehicle(
                vehicleId=vehicle.vehicle_id,
                type=vehicle.type,
                registration=vehicle.registration,
                status=vehicle.status,
                make=vehicle.make,
                model=vehicle.model,
                color=vehicle.color,
            )
        )

    return vehicles


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
