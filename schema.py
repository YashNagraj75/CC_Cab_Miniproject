from enum import Enum
from typing import Any, Dict, List, Optional

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


class BookingStatus(str, Enum):
    SEARCHING = "searching"
    CONFIRMED = "confirmed"
    DRIVER_ARRIVED = "driver_arrived"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# Pydantic models for request/response validation
class Location(BaseModel):
    latitude: float
    longitude: float
    address: Optional[str] = None


class FareInfo(BaseModel):
    currency: str
    amount: float
    breakdown: Optional[Dict[str, float]] = None


class DriverInfo(BaseModel):
    driverId: str
    name: str
    phone: str
    rating: float


class VehicleInfo(BaseModel):
    vehicleId: str
    make: str
    model: str
    color: str
    registration: str


class BookingRequest(BaseModel):
    userId: str
    pickupLocation: Location
    dropoffLocation: Location
    vehicleType: str
    paymentMethodId: str


class BookingResponse(BaseModel):
    bookingId: str
    status: BookingStatus
    estimatedFare: Optional[FareInfo] = None
    message: Optional[str] = None


class BookingDetail(BaseModel):
    bookingId: str
    userId: str
    status: BookingStatus
    pickupLocation: Location
    dropoffLocation: Location
    vehicleType: str
    estimatedFare: Optional[FareInfo] = None
    actualFare: Optional[FareInfo] = None
    driverInfo: Optional[DriverInfo] = None
    vehicleInfo: Optional[VehicleInfo] = None
    createdAt: str
    updatedAt: str
    eta: Optional[int] = None  # ETA in minutes


class CancelBookingRequest(BaseModel):
    reason: Optional[str] = None


class CancelBookingResponse(BaseModel):
    bookingId: str
    status: BookingStatus
    message: str
    cancellationFee: Optional[FareInfo] = None


class PaginatedBookings(BaseModel):
    data: List[BookingDetail]
    pagination: Dict[str, Any]
