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
