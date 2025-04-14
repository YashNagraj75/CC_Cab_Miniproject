-- Enable foreign key constraints (IMPORTANT: Execute this first)
PRAGMA foreign_keys = ON;

-- Create tables with proper relationships and constraints

-- Partners table
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

-- Vehicles table
CREATE TABLE vehicles (
    vehicle_id TEXT PRIMARY KEY,
    partner_id TEXT NOT NULL,
    type TEXT NOT NULL,
    make TEXT,
    model TEXT,
    color TEXT,
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
    location_id INTEGER PRIMARY KEY AUTOINCREMENT, -- Use INTEGER for AUTOINCREMENT
    vehicle_id TEXT NOT NULL,
    latitude REAL NOT NULL,  -- Use REAL for DECIMAL
    longitude REAL NOT NULL, -- Use REAL for DECIMAL
    accuracy REAL,           -- Use REAL for DECIMAL
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_locations_vehicle_id FOREIGN KEY (vehicle_id)
        REFERENCES vehicles(vehicle_id) ON DELETE CASCADE ON UPDATE CASCADE
);

-- Index for geospatial queries (Syntax is the same)
CREATE INDEX idx_vehicle_locations_coords ON vehicle_locations(latitude, longitude);

-- Drivers table
CREATE TABLE drivers (
    driver_id TEXT PRIMARY KEY,
    partner_id TEXT NOT NULL,
    vehicle_id TEXT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT,
    license_number TEXT NOT NULL,
    average_rating REAL DEFAULT 0.0, -- Use REAL for DECIMAL
    status TEXT NOT NULL DEFAULT 'offline' CHECK (status IN ('online', 'offline', 'on_ride', 'on_break')),
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
    area_id INTEGER PRIMARY KEY AUTOINCREMENT, -- Use INTEGER for AUTOINCREMENT
    partner_id TEXT NOT NULL,
    city TEXT NOT NULL,
    region TEXT,
    country TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)), -- Use INTEGER for BOOLEAN

    CONSTRAINT fk_service_areas_partner_id FOREIGN KEY (partner_id)
        REFERENCES partners(partner_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT uk_partner_service_area UNIQUE (partner_id, city, region, country)
);

-- Partner documents table
CREATE TABLE partner_documents (
    document_id INTEGER PRIMARY KEY AUTOINCREMENT, -- Use INTEGER for AUTOINCREMENT
    partner_id TEXT NOT NULL,
    document_type TEXT NOT NULL CHECK (document_type IN ('business_license', 'insurance', 'tax_certificate', 'other')),
    document_number TEXT,
    document_url TEXT,
    expiry_date TEXT, -- Store DATE as TEXT 'YYYY-MM-DD'
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
    document_id INTEGER PRIMARY KEY AUTOINCREMENT, -- Use INTEGER for AUTOINCREMENT
    vehicle_id TEXT NOT NULL,
    document_type TEXT NOT NULL CHECK (document_type IN ('registration', 'insurance', 'fitness_certificate', 'permit', 'other')),
    document_number TEXT,
    document_url TEXT,
    expiry_date TEXT, -- Store DATE as TEXT 'YYYY-MM-DD'
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
    document_id INTEGER PRIMARY KEY AUTOINCREMENT, -- Use INTEGER for AUTOINCREMENT
    driver_id TEXT NOT NULL,
    document_type TEXT NOT NULL CHECK (document_type IN ('driving_license', 'identity', 'background_check', 'other')),
    document_number TEXT,
    document_url TEXT,
    expiry_date TEXT, -- Store DATE as TEXT 'YYYY-MM-DD'
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

-- Create indexes (Syntax is the same)
CREATE INDEX idx_partners_status ON partners(status);
CREATE INDEX idx_vehicles_status ON vehicles(status);
CREATE INDEX idx_drivers_status ON drivers(status);
CREATE INDEX idx_partners_name ON partners(name);
CREATE INDEX idx_vehicles_type ON vehicles(type);

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
    COUNT(DISTINCT CASE WHEN d.status = 'online' THEN d.driver_id END) AS online_drivers,
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
    d.first_name || ' ' || d.last_name AS driver_name, -- Use || for concatenation
    d.status AS driver_status,
    d.average_rating
FROM vehicles v
JOIN partners p ON v.partner_id = p.partner_id
LEFT JOIN drivers d ON v.vehicle_id = d.vehicle_id;

-- Sample data insertion - Partners (Syntax is the same)
INSERT INTO partners (partner_id, name, phone, email, address) VALUES
('partner123', 'ABC Cabs', '9876543210', 'contact@abccabs.com', '123 Main Street, Mumbai'),
('partner456', 'XYZ Rides', '9988776655', 'support@xyzrides.com', '456 Park Avenue, Delhi'),
('partner789', 'Quick Cabs', '8877665544', 'info@quickcabs.com', '789 Lake Road, Bangalore');

-- Sample data insertion - Vehicles (Syntax is the same)
INSERT INTO vehicles (vehicle_id, partner_id, type, make, model, color, registration) VALUES
('veh123', 'partner123', 'Sedan', 'Toyota', 'Corolla', 'White', 'MH01AB1234'),
('veh456', 'partner123', 'SUV', 'Honda', 'CR-V', 'Black', 'MH01CD5678'),
('veh789', 'partner456', 'Hatchback', 'Maruti', 'Swift', 'Red', 'DL01EF9012'),
('veh101', 'partner456', 'Sedan', 'Hyundai', 'Verna', 'Silver', 'DL01GH3456'),
('veh202', 'partner789', 'SUV', 'Mahindra', 'XUV500', 'Blue', 'KA01IJ7890');

-- Sample data insertion - Drivers (Syntax is the same)
INSERT INTO drivers (driver_id, partner_id, vehicle_id, first_name, last_name, phone, email, license_number, status) VALUES
('driver123', 'partner123', 'veh123', 'Amit', 'Kumar', '9876543001', 'amit.k@example.com', 'DL98765432', 'online'),
('driver456', 'partner123', 'veh456', 'Raj', 'Singh', '9876543002', 'raj.s@example.com', 'DL87654321', 'offline'),
('driver789', 'partner456', 'veh789', 'Priya', 'Sharma', '9876543003', 'priya.s@example.com', 'DL76543210', 'online'),
('driver101', 'partner456', 'veh101', 'Neha', 'Patel', '9876543004', 'neha.p@example.com', 'DL65432109', 'on_ride'),
('driver202', 'partner789', 'veh202', 'Suresh', 'Verma', '9876543005', 'suresh.v@example.com', 'DL54321098', 'online');

-- Sample data insertion - Service Areas (Use 1 for TRUE)
INSERT INTO partner_service_areas (partner_id, city, region, country, active) VALUES
('partner123', 'Mumbai', 'Maharashtra', 'India', 1),
('partner123', 'Pune', 'Maharashtra', 'India', 1),
('partner456', 'Delhi', 'Delhi', 'India', 1),
('partner456', 'Gurgaon', 'Haryana', 'India', 1),
('partner789', 'Bangalore', 'Karnataka', 'India', 1);
