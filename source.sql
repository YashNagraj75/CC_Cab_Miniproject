-- Enable foreign key constraints (IMPORTANT: Execute this first)
PRAGMA foreign_keys = ON;

-- Create tables with proper relationships and constraints

-- Partners table (merged from both schemas)
CREATE TABLE partners (
    partner_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    address TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uk_partners_email UNIQUE (email),
    CONSTRAINT uk_partners_phone UNIQUE (phone)
);

-- Trigger for partners updated_at
CREATE TRIGGER trigger_partners_updated_at
AFTER UPDATE ON partners
FOR EACH ROW
BEGIN
    UPDATE partners SET updated_at = CURRENT_TIMESTAMP WHERE partner_id = OLD.partner_id;
END;

-- Users table (from cab-booking-schema)
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uk_users_email UNIQUE (email),
    CONSTRAINT uk_users_phone UNIQUE (phone)
);

-- Trigger for users updated_at
CREATE TRIGGER trigger_users_updated_at
AFTER UPDATE ON users
FOR EACH ROW
BEGIN
    UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE user_id = OLD.user_id;
END;

-- Vehicles table (merged from both schemas)
CREATE TABLE vehicles (
    vehicle_id TEXT PRIMARY KEY,
    partner_id TEXT NOT NULL,
    type TEXT NOT NULL,
    make TEXT NOT NULL,
    model TEXT NOT NULL,
    color TEXT NOT NULL,
    registration TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'on_ride', 'offline')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_vehicles_partner_id FOREIGN KEY (partner_id)
        REFERENCES partners(partner_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT uk_vehicles_registration UNIQUE (registration)
);

-- Trigger for vehicles updated_at
CREATE TRIGGER trigger_vehicles_updated_at
AFTER UPDATE ON vehicles
FOR EACH ROW
BEGIN
    UPDATE vehicles SET updated_at = CURRENT_TIMESTAMP WHERE vehicle_id = OLD.vehicle_id;
END;

-- Vehicle locations table
CREATE TABLE vehicle_locations (
    location_id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    accuracy REAL,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_locations_vehicle_id FOREIGN KEY (vehicle_id)
        REFERENCES vehicles(vehicle_id) ON DELETE CASCADE ON UPDATE CASCADE
);

-- Index for geospatial queries
CREATE INDEX idx_vehicle_locations_coords ON vehicle_locations(latitude, longitude);

-- Drivers table (merged from both schemas)
CREATE TABLE drivers (
    driver_id TEXT PRIMARY KEY,
    partner_id TEXT NOT NULL,
    vehicle_id TEXT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT,
    license_number TEXT NOT NULL,
    average_rating REAL DEFAULT 0.0,
    total_reviews INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'offline' CHECK (status IN ('online', 'offline', 'on_ride', 'on_break', 'available')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_drivers_partner_id FOREIGN KEY (partner_id)
        REFERENCES partners(partner_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_drivers_vehicle_id FOREIGN KEY (vehicle_id)
        REFERENCES vehicles(vehicle_id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT uk_drivers_phone UNIQUE (phone),
    CONSTRAINT uk_drivers_email UNIQUE (email),
    CONSTRAINT uk_drivers_license UNIQUE (license_number)
);

-- Trigger for drivers updated_at
CREATE TRIGGER trigger_drivers_updated_at
AFTER UPDATE ON drivers
FOR EACH ROW
BEGIN
    UPDATE drivers SET updated_at = CURRENT_TIMESTAMP WHERE driver_id = OLD.driver_id;
END;

-- Partner service areas table
CREATE TABLE partner_service_areas (
    area_id INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_id TEXT NOT NULL,
    city TEXT NOT NULL,
    region TEXT,
    country TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),

    CONSTRAINT fk_service_areas_partner_id FOREIGN KEY (partner_id)
        REFERENCES partners(partner_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT uk_partner_service_area UNIQUE (partner_id, city, region, country)
);

-- Partner documents table
CREATE TABLE partner_documents (
    document_id INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_id TEXT NOT NULL,
    document_type TEXT NOT NULL CHECK (document_type IN ('business_license', 'insurance', 'tax_certificate', 'other')),
    document_number TEXT,
    document_url TEXT,
    expiry_date TEXT,
    verification_status TEXT NOT NULL DEFAULT 'pending' CHECK (verification_status IN ('pending', 'verified', 'rejected')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_documents_partner_id FOREIGN KEY (partner_id)
        REFERENCES partners(partner_id) ON DELETE CASCADE ON UPDATE CASCADE
);

-- Trigger for partner_documents updated_at
CREATE TRIGGER trigger_partner_documents_updated_at
AFTER UPDATE ON partner_documents
FOR EACH ROW
BEGIN
    UPDATE partner_documents SET updated_at = CURRENT_TIMESTAMP WHERE document_id = OLD.document_id;
END;

-- Vehicle documents table
CREATE TABLE vehicle_documents (
    document_id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id TEXT NOT NULL,
    document_type TEXT NOT NULL CHECK (document_type IN ('registration', 'insurance', 'fitness_certificate', 'permit', 'other')),
    document_number TEXT,
    document_url TEXT,
    expiry_date TEXT,
    verification_status TEXT NOT NULL DEFAULT 'pending' CHECK (verification_status IN ('pending', 'verified', 'rejected')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_vehicle_docs_vehicle_id FOREIGN KEY (vehicle_id)
        REFERENCES vehicles(vehicle_id) ON DELETE CASCADE ON UPDATE CASCADE
);

-- Trigger for vehicle_documents updated_at
CREATE TRIGGER trigger_vehicle_documents_updated_at
AFTER UPDATE ON vehicle_documents
FOR EACH ROW
BEGIN
    UPDATE vehicle_documents SET updated_at = CURRENT_TIMESTAMP WHERE document_id = OLD.document_id;
END;

-- Driver documents table
CREATE TABLE driver_documents (
    document_id INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_id TEXT NOT NULL,
    document_type TEXT NOT NULL CHECK (document_type IN ('driving_license', 'identity', 'background_check', 'other')),
    document_number TEXT,
    document_url TEXT,
    expiry_date TEXT,
    verification_status TEXT NOT NULL DEFAULT 'pending' CHECK (verification_status IN ('pending', 'verified', 'rejected')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_driver_docs_driver_id FOREIGN KEY (driver_id)
        REFERENCES drivers(driver_id) ON DELETE CASCADE ON UPDATE CASCADE
);

-- Trigger for driver_documents updated_at
CREATE TRIGGER trigger_driver_documents_updated_at
AFTER UPDATE ON driver_documents
FOR EACH ROW
BEGIN
    UPDATE driver_documents SET updated_at = CURRENT_TIMESTAMP WHERE document_id = OLD.document_id;
END;

-- Driver locations table (from cab-booking-schema)
CREATE TABLE driver_locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_id TEXT NOT NULL,
    booking_id TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (driver_id) REFERENCES drivers (driver_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (booking_id) REFERENCES bookings (booking_id) ON DELETE SET NULL ON UPDATE CASCADE
);

-- Payment methods table (from cab-booking-schema)
CREATE TABLE payment_methods (
    payment_method_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    method_type TEXT NOT NULL,
    details TEXT,
    is_default INTEGER DEFAULT 0 CHECK (is_default IN (0, 1)),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE ON UPDATE CASCADE
);

-- Trigger for payment_methods updated_at
CREATE TRIGGER trigger_payment_methods_updated_at
AFTER UPDATE ON payment_methods
FOR EACH ROW
BEGIN
    UPDATE payment_methods SET updated_at = CURRENT_TIMESTAMP WHERE payment_method_id = OLD.payment_method_id;
END;

-- Bookings table (from cab-booking-schema)
CREATE TABLE bookings (
    booking_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    driver_id TEXT,
    vehicle_id TEXT,
    status TEXT CHECK (status IN ('searching', 'confirmed', 'driver_arrived', 'ongoing', 'completed', 'cancelled')) NOT NULL DEFAULT 'searching',
    pickup_latitude REAL NOT NULL,
    pickup_longitude REAL NOT NULL,
    pickup_address TEXT,
    dropoff_latitude REAL NOT NULL,
    dropoff_longitude REAL NOT NULL,
    dropoff_address TEXT,
    vehicle_type TEXT NOT NULL,
    payment_method_id TEXT NOT NULL,
    estimated_fare_amount REAL,
    estimated_fare_currency TEXT DEFAULT 'INR',
    actual_fare_amount REAL,
    actual_fare_currency TEXT DEFAULT 'INR',
    cancellation_reason TEXT,
    cancellation_fee_amount REAL,
    estimated_distance REAL,
    estimated_duration INTEGER,
    actual_distance REAL,
    actual_duration INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (driver_id) REFERENCES drivers (driver_id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles (vehicle_id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (payment_method_id) REFERENCES payment_methods (payment_method_id) ON DELETE CASCADE ON UPDATE CASCADE
);

-- Trigger for bookings updated_at
CREATE TRIGGER trigger_bookings_updated_at
AFTER UPDATE ON bookings
FOR EACH ROW
BEGIN
    UPDATE bookings SET updated_at = CURRENT_TIMESTAMP WHERE booking_id = OLD.booking_id;
END;

-- Booking status history table (from cab-booking-schema)
CREATE TABLE booking_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (booking_id) REFERENCES bookings (booking_id) ON DELETE CASCADE ON UPDATE CASCADE
);

-- Reviews table (from cab-booking-schema, enhanced)
CREATE TABLE reviews (
    review_id TEXT PRIMARY KEY,
    booking_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    driver_id TEXT NOT NULL,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5) NOT NULL,
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (booking_id) REFERENCES bookings (booking_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (driver_id) REFERENCES drivers (driver_id) ON DELETE CASCADE ON UPDATE CASCADE
);

-- Fare calculations table (from cab-booking-schema)
CREATE TABLE fare_calculations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id TEXT NOT NULL,
    base_fare REAL NOT NULL,
    distance_charge REAL NOT NULL,
    time_charge REAL NOT NULL,
    surge_multiplier REAL DEFAULT 1.0,
    other_charges REAL DEFAULT 0.0,
    tax_amount REAL DEFAULT 0.0,
    total_amount REAL NOT NULL,
    currency TEXT DEFAULT 'INR',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (booking_id) REFERENCES bookings (booking_id) ON DELETE CASCADE ON UPDATE CASCADE
);

-- Create indexes
CREATE INDEX idx_partners_status ON partners(status);
CREATE INDEX idx_vehicles_status ON vehicles(status);
CREATE INDEX idx_drivers_status ON drivers(status);
CREATE INDEX idx_partners_name ON partners(name);
CREATE INDEX idx_vehicles_type ON vehicles(type);
CREATE INDEX idx_bookings_user_id ON bookings(user_id);
CREATE INDEX idx_bookings_driver_id ON bookings(driver_id);
CREATE INDEX idx_bookings_status ON bookings(status);
CREATE INDEX idx_reviews_driver_id ON reviews(driver_id);
CREATE INDEX idx_driver_locations_driver_id ON driver_locations(driver_id);
CREATE INDEX idx_vehicles_partner_id ON vehicles(partner_id);

-- Create view for active partners with vehicle counts
CREATE VIEW view_active_partners_summary AS
SELECT
    p.partner_id,
    p.name,
    p.phone,
    p.email,
    p.status,
    COUNT(DISTINCT v.vehicle_id) AS total_vehicles,
    COUNT(DISTINCT d.driver_id) AS total_drivers,
    COUNT(DISTINCT CASE WHEN v.status = 'available' THEN v.vehicle_id END) AS available_vehicles,
    COUNT(DISTINCT CASE WHEN d.status IN ('online', 'available') THEN d.driver_id END) AS online_drivers,
    p.created_at,
    p.updated_at
FROM partners p
LEFT JOIN vehicles v ON p.partner_id = v.partner_id
LEFT JOIN drivers d ON p.partner_id = d.partner_id
WHERE p.status = 'active'
GROUP BY p.partner_id, p.name, p.phone, p.email, p.status, p.created_at, p.updated_at;

-- Create view for vehicle details with partner info
CREATE VIEW view_vehicle_details AS
SELECT
    v.vehicle_id,
    v.registration,
    v.type,
    v.make,
    v.model,
    v.color,
    v.status AS vehicle_status,
    p.partner_id,
    p.name AS partner_name,
    d.driver_id,
    d.first_name || ' ' || d.last_name AS driver_name,
    d.status AS driver_status,
    d.average_rating
FROM vehicles v
JOIN partners p ON v.partner_id = p.partner_id
LEFT JOIN drivers d ON v.vehicle_id = d.vehicle_id;

-- Create view for booking details with user, driver, and vehicle info
CREATE VIEW view_booking_details AS
SELECT
    b.booking_id,
    b.status AS booking_status,
    b.created_at AS booking_time,
    u.user_id,
    u.name AS user_name,
    d.driver_id,
    d.first_name || ' ' || d.last_name AS driver_name,
    v.vehicle_id,
    v.registration,
    v.make,
    v.model,
    v.color,
    b.pickup_address,
    b.dropoff_address,
    b.estimated_fare_amount,
    b.actual_fare_amount,
    b.estimated_distance,
    b.actual_distance,
    b.estimated_duration,
    b.actual_duration
FROM bookings b
JOIN users u ON b.user_id = u.user_id
LEFT JOIN drivers d ON b.driver_id = d.driver_id
LEFT JOIN vehicles v ON b.vehicle_id = v.vehicle_id;

-- Sample data insertion - Partners
INSERT INTO partners (partner_id, name, phone, email, address) VALUES
('partner123', 'ABC Cabs', '9876543210', 'contact@abccabs.com', '123 Main Street, Mumbai'),
('partner456', 'XYZ Rides', '9988776655', 'support@xyzrides.com', '456 Park Avenue, Delhi'),
('partner789', 'Quick Cabs', '8877665544', 'info@quickcabs.com', '789 Lake Road, Bangalore');

-- Sample data insertion - Users
INSERT INTO users (user_id, name, phone, email) VALUES
('user123', 'Test User', '9876543220', 'test@example.com'),
('user456', 'John Doe', '9876543221', 'john@example.com'),
('user789', 'Jane Smith', '9876543222', 'jane@example.com');

-- Sample data insertion - Vehicles
INSERT INTO vehicles (vehicle_id, partner_id, type, make, model, color, registration) VALUES
('veh123', 'partner123', 'Sedan', 'Toyota', 'Corolla', 'White', 'MH01AB1234'),
('veh456', 'partner123', 'SUV', 'Honda', 'CR-V', 'Black', 'MH01CD5678'),
('veh789', 'partner456', 'Hatchback', 'Maruti', 'Swift', 'Red', 'DL01EF9012'),
('veh101', 'partner456', 'Sedan', 'Hyundai', 'Verna', 'Silver', 'DL01GH3456'),
('veh202', 'partner789', 'SUV', 'Mahindra', 'XUV500', 'Blue', 'KA01IJ7890');

-- Sample data insertion - Drivers
INSERT INTO drivers (driver_id, partner_id, vehicle_id, first_name, last_name, phone, email, license_number, status) VALUES
('driver123', 'partner123', 'veh123', 'Amit', 'Kumar', '9876543001', 'amit.k@example.com', 'DL98765432', 'online'),
('driver456', 'partner123', 'veh456', 'Raj', 'Singh', '9876543002', 'raj.s@example.com', 'DL87654321', 'offline'),
('driver789', 'partner456', 'veh789', 'Priya', 'Sharma', '9876543003', 'priya.s@example.com', 'DL76543210', 'online'),
('driver101', 'partner456', 'veh101', 'Neha', 'Patel', '9876543004', 'neha.p@example.com', 'DL65432109', 'on_ride'),
('driver202', 'partner789', 'veh202', 'Suresh', 'Verma', '9876543005', 'suresh.v@example.com', 'DL54321098', 'online');

-- Sample data insertion - Service Areas
INSERT INTO partner_service_areas (partner_id, city, region, country, active) VALUES
('partner123', 'Mumbai', 'Maharashtra', 'India', 1),
('partner123', 'Pune', 'Maharashtra', 'India', 1),
('partner456', 'Delhi', 'Delhi', 'India', 1),
('partner456', 'Gurgaon', 'Haryana', 'India', 1),
('partner789', 'Bangalore', 'Karnataka', 'India', 1);

-- Sample data insertion - Payment Methods
INSERT INTO payment_methods (payment_method_id, user_id, method_type, details, is_default) VALUES
('pay123', 'user123', 'credit_card', '{"last4": "1234", "brand": "visa"}', 1),
('pay456', 'user456', 'upi', '{"upi_id": "johndoe@upi"}', 1),
('pay789', 'user789', 'wallet', '{"wallet_id": "wallet123"}', 1);

-- Sample data insertion - Bookings
INSERT INTO bookings (
    booking_id, user_id, driver_id, vehicle_id, status,
    pickup_latitude, pickup_longitude, pickup_address,
    dropoff_latitude, dropoff_longitude, dropoff_address,
    vehicle_type, payment_method_id, estimated_fare_amount,
    estimated_distance, estimated_duration
) VALUES
(
    'booking123', 'user123', 'driver123', 'veh123', 'confirmed',
    12.9716, 77.5946, '123 MG Road, Bangalore',
    12.9352, 77.6245, '456 Koramangala, Bangalore',
    'Sedan', 'pay123', 250.50,
    15.2, 35
),
(
    'booking456', 'user456', 'driver789', 'veh789', 'completed',
    19.0760, 72.8777, '789 Andheri, Mumbai',
    19.1138, 72.8973, '123 Powai, Mumbai',
    'Hatchback', 'pay456', 180.75,
    12.5, 28
);

-- Sample data insertion - Booking Status History
INSERT INTO booking_status_history (booking_id, status) VALUES
('booking123', 'searching'),
('booking123', 'confirmed'),
('booking456', 'searching'),
('booking456', 'confirmed'),
('booking456', 'driver_arrived'),
('booking456', 'ongoing'),
('booking456', 'completed');

-- Sample data insertion - Reviews
INSERT INTO reviews (review_id, booking_id, user_id, driver_id, rating, comment) VALUES
('review123', 'booking456', 'user456', 'driver789', 5, 'Excellent driver, very polite and clean car!');

-- Sample data insertion - Fare Calculations
INSERT INTO fare_calculations (booking_id, base_fare, distance_charge, time_charge, surge_multiplier, tax_amount, total_amount) VALUES
('booking456', 50.00, 90.75, 28.00, 1.0, 12.00, 180.75);
