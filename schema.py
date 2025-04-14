from typing import Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


# Pydantic models (same as before)
class ContactInfo(BaseModel):
    phone: str
    email: str


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
    createdAt: str
    updatedAt: str


class CabPartnerListResponse(BaseModel):
    data: List[CabPartnerResponse]
    pagination: Dict[str, int]


class MessageResponse(BaseModel):
    partnerId: str
    message: str
