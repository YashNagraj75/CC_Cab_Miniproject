PRAGMA foreign_keys = ON;

-- Create the admins table if it doesn't already exist
CREATE TABLE IF NOT EXISTS admins (
    username TEXT PRIMARY KEY NOT NULL, -- Unique identifier for the admin user
    hashed_password TEXT NOT NULL,     -- Securely hashed password
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Timestamp of creation
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP  -- Timestamp of last update
);

-- Trigger for admins updated_at
-- Automatically updates the updated_at column whenever an admin row is modified.
CREATE TRIGGER IF NOT EXISTS trigger_admins_updated_at
AFTER UPDATE ON admins
FOR EACH ROW
BEGIN
    UPDATE admins SET updated_at = CURRENT_TIMESTAMP WHERE username = OLD.username;
END;

