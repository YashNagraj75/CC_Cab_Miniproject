import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt  # Import from PyJWT
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# --- Configuration ---
# !! Important: Use environment variables for sensitive data in production !!
SECRET_KEY = "your-strong-secret-key-here"  # CHANGE THIS! Keep it secret.
ALGORITHM = "HS256"  # PyJWT supports HS256
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # Token validity period

# Database connection (same as your main service)
SQLALCHEMY_DATABASE_URL = (
    "sqlite:///./data.db"  # Assumes data.db is in the same directory
)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Password Hashing Setup ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- Pydantic Models ---
class AdminBase(BaseModel):
    username: str


class AdminCreate(AdminBase):
    password: str


class AdminLogin(AdminBase):
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    # Standard claim for subject is 'sub'
    sub: Optional[str] = None


# --- Database Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Security Utilities ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# --- UPDATED JWT FUNCTION using PyJWT ---
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Creates a JWT access token using PyJWT."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )

    # Add standard claims: 'exp' (expiration), 'iat' (issued at), 'sub' (subject)
    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            # 'sub' should already be in the data passed from the login function
        }
    )
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# --- FastAPI App ---
app = FastAPI(
    title="Admin Login Service (PyJWT)",
    description="Microservice for Admin User Registration and Login using PyJWT",
)

# --- Endpoints ---


@app.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new Admin User",
)
async def register_admin(admin: AdminCreate, db: Session = Depends(get_db)):
    """Registers a new admin user. Passwords are hashed before storing."""
    check_user_query = text("SELECT username FROM admins WHERE username = :username")
    existing_user = db.execute(
        check_user_query, {"username": admin.username}
    ).fetchone()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    hashed_pass = hash_password(admin.password)

    insert_user_query = text("""
        INSERT INTO admins (username, hashed_password)
        VALUES (:username, :hashed_password)
    """)
    try:
        db.execute(
            insert_user_query,
            {"username": admin.username, "hashed_password": hashed_pass},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error registering admin: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not register admin user.",
        )

    return {"message": f"Admin user '{admin.username}' registered successfully"}


@app.post("/login", response_model=Token, summary="Admin User Login")
async def login_for_access_token(form_data: AdminLogin, db: Session = Depends(get_db)):
    """Authenticates an admin user and returns a JWT access token upon success."""
    get_user_query = text(
        "SELECT username, hashed_password FROM admins WHERE username = :username"
    )
    db_user_result = db.execute(
        get_user_query, {"username": form_data.username}
    ).fetchone()

    if not db_user_result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if hasattr(db_user_result, "_mapping"):
        db_user = dict(db_user_result._mapping)
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing user data.",
        )

    hashed_password = db_user.get("hashed_password")

    if not hashed_password or not verify_password(form_data.password, hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        # Pass the username as the 'sub' (subject) claim
        data={"sub": form_data.username},
        expires_delta=access_token_expires,
    )

    return {"access_token": access_token, "token_type": "bearer"}


# Optional: Root endpoint
@app.get("/", tags=["Status"])
async def read_root():
    return {"status": "OK", "service": "Admin Login Service", "jwt_library": "PyJWT"}
