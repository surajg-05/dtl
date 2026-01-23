from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
import sqlite3
import os
import re
import base64
import random
import json

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="CampusPool API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SQLite Database Setup
DATABASE_PATH = os.environ.get("SQLITE_DB_PATH", "/app/backend/campuspool.db")

def get_db():
    """Get database connection with row factory for dict-like access"""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """Initialize SQLite database with all required tables"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('rider', 'driver', 'admin')),
            is_admin INTEGER DEFAULT 0,
            verification_status TEXT DEFAULT 'unverified',
            student_id_image TEXT,
            rejection_reason TEXT,
            verified_at TEXT,
            vehicle_model TEXT,
            vehicle_number TEXT,
            vehicle_color TEXT,
            branch TEXT,
            academic_year TEXT,
            is_active INTEGER DEFAULT 1,
            is_suspended INTEGER DEFAULT 0,
            warning_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    
    # Rides table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            destination TEXT NOT NULL,
            source_lat REAL,
            source_lng REAL,
            destination_lat REAL,
            destination_lng REAL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            available_seats INTEGER NOT NULL,
            estimated_cost REAL NOT NULL,
            status TEXT DEFAULT 'active',
            pickup_point TEXT,
            is_recurring INTEGER DEFAULT 0,
            recurrence_pattern TEXT,
            parent_ride_id INTEGER,
            event_tag INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (driver_id) REFERENCES users(id),
            FOREIGN KEY (parent_ride_id) REFERENCES rides(id),
            FOREIGN KEY (event_tag) REFERENCES event_tags(id)
        )
    """)
    
    # Ride Requests table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ride_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ride_id INTEGER NOT NULL,
            rider_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            ride_pin TEXT,
            ride_started_at TEXT,
            reached_safely_at TEXT,
            completed_at TEXT,
            is_urgent INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (ride_id) REFERENCES rides(id),
            FOREIGN KEY (rider_id) REFERENCES users(id)
        )
    """)
    
    # Chat Messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ride_request_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (ride_request_id) REFERENCES ride_requests(id),
            FOREIGN KEY (sender_id) REFERENCES users(id)
        )
    """)
    
    # SOS Events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sos_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ride_request_id INTEGER NOT NULL,
            triggered_by INTEGER NOT NULL,
            latitude REAL,
            longitude REAL,
            location_text TEXT,
            message TEXT,
            status TEXT DEFAULT 'active',
            admin_notes TEXT,
            reviewed_at TEXT,
            resolved_at TEXT,
            resolved_by INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (ride_request_id) REFERENCES ride_requests(id),
            FOREIGN KEY (triggered_by) REFERENCES users(id),
            FOREIGN KEY (resolved_by) REFERENCES users(id)
        )
    """)
    
    # Ratings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ride_request_id INTEGER NOT NULL,
            rater_id INTEGER NOT NULL,
            rated_user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
            feedback TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (ride_request_id) REFERENCES ride_requests(id),
            FOREIGN KEY (rater_id) REFERENCES users(id),
            FOREIGN KEY (rated_user_id) REFERENCES users(id)
        )
    """)
    
    # Event Tags table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)
    
    # Reports table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id INTEGER NOT NULL,
            reported_user_id INTEGER,
            ride_id INTEGER,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            admin_action TEXT,
            admin_notes TEXT,
            handled_at TEXT,
            handled_by INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (reporter_id) REFERENCES users(id),
            FOREIGN KEY (reported_user_id) REFERENCES users(id),
            FOREIGN KEY (ride_id) REFERENCES rides(id),
            FOREIGN KEY (handled_by) REFERENCES users(id)
        )
    """)
    
    # Audit Logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            admin_name TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            details TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (admin_id) REFERENCES users(id)
        )
    """)
    
    conn.commit()
    conn.close()
    print("SQLite database initialized successfully!")

# Initialize database on startup
init_db()

# JWT Config
JWT_SECRET = os.environ.get("JWT_SECRET", "campuspool-secret-key-2024")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# Allowed email domain
ALLOWED_EMAIL_DOMAIN = "@rvce.edu.in"

# Phase 5: RVCE-specific Pickup Points
PICKUP_POINTS = [
    {"id": "main_gate", "name": "Main Gate", "description": "RVCE Main Entrance"},
    {"id": "library", "name": "Central Library", "description": "Near Library Building"},
    {"id": "canteen", "name": "Main Canteen", "description": "Central Canteen Area"},
    {"id": "cse_block", "name": "CSE Block", "description": "Computer Science Building"},
    {"id": "ece_block", "name": "ECE Block", "description": "Electronics Building"},
    {"id": "mech_block", "name": "Mechanical Block", "description": "Mechanical Engineering Building"},
    {"id": "civil_block", "name": "Civil Block", "description": "Civil Engineering Building"},
    {"id": "admin_block", "name": "Admin Block", "description": "Administrative Building"},
    {"id": "hostel_gate", "name": "Hostel Gate", "description": "Boys/Girls Hostel Entrance"},
    {"id": "sports_complex", "name": "Sports Complex", "description": "Near Playground/Gym"},
    {"id": "parking_lot", "name": "Parking Lot", "description": "Main Parking Area"},
    {"id": "back_gate", "name": "Back Gate", "description": "Rear Campus Exit"},
]

# Phase 5: Recurrence Patterns
RECURRENCE_PATTERNS = [
    {"id": "weekdays", "name": "Weekdays", "days": [0, 1, 2, 3, 4]},
    {"id": "weekends", "name": "Weekends", "days": [5, 6]},
    {"id": "daily", "name": "Daily", "days": [0, 1, 2, 3, 4, 5, 6]},
    {"id": "mon_wed_fri", "name": "Mon/Wed/Fri", "days": [0, 2, 4]},
    {"id": "tue_thu", "name": "Tue/Thu", "days": [1, 3]},
]

# Phase 7: RVCE Branches and Academic Years
BRANCHES = [
    {"id": "cse", "name": "Computer Science"},
    {"id": "ise", "name": "Information Science"},
    {"id": "ece", "name": "Electronics & Communication"},
    {"id": "eee", "name": "Electrical & Electronics"},
    {"id": "me", "name": "Mechanical Engineering"},
    {"id": "cv", "name": "Civil Engineering"},
    {"id": "bt", "name": "Biotechnology"},
    {"id": "ch", "name": "Chemical Engineering"},
    {"id": "im", "name": "Industrial Management"},
    {"id": "te", "name": "Telecommunication"},
]

ACADEMIC_YEARS = [
    {"id": "1", "name": "1st Year"},
    {"id": "2", "name": "2nd Year"},
    {"id": "3", "name": "3rd Year"},
    {"id": "4", "name": "4th Year"},
]

# Phase 7: Badge Definitions
BADGE_DEFINITIONS = [
    {"id": "first_ride", "name": "First Ride", "description": "Completed your first ride", "icon": "🎉", "threshold": 1},
    {"id": "rides_5", "name": "Rising Star", "description": "Completed 5 rides", "icon": "⭐", "threshold": 5},
    {"id": "rides_10", "name": "Road Warrior", "description": "Completed 10 rides", "icon": "🏆", "threshold": 10},
    {"id": "rides_25", "name": "Campus Hero", "description": "Completed 25 rides", "icon": "🦸", "threshold": 25},
    {"id": "eco_warrior", "name": "Eco Warrior", "description": "Saved 50kg CO2", "icon": "🌱", "threshold_co2": 50},
    {"id": "eco_champion", "name": "Eco Champion", "description": "Saved 100kg CO2", "icon": "🌍", "threshold_co2": 100},
]

# Phase 7: CO2 Constants
CO2_PER_KM_SAVED = 0.21
AVG_RIDE_DISTANCE_KM = 8
COST_PER_KM_SOLO = 12

# Pydantic Models
class UserSignup(BaseModel):
    email: str
    password: str
    name: str
    role: str = Field(..., pattern="^(rider|driver)$")

class UserLogin(BaseModel):
    email: str
    password: str

class UserProfile(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    vehicle_model: Optional[str] = None
    vehicle_number: Optional[str] = None
    vehicle_color: Optional[str] = None

class RideCreate(BaseModel):
    source: str
    destination: str
    source_lat: Optional[float] = None
    source_lng: Optional[float] = None
    destination_lat: Optional[float] = None
    destination_lng: Optional[float] = None
    date: str
    time: str
    available_seats: int = Field(..., ge=1, le=10)
    estimated_cost: float = Field(..., ge=0)
    pickup_point: Optional[str] = None
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None
    recurrence_days_ahead: Optional[int] = Field(default=None, ge=1, le=30)
    event_tag: Optional[str] = None
    is_offline_mode: bool = False  # Flag for offline location entry

class RideUpdate(BaseModel):
    source: Optional[str] = None
    destination: Optional[str] = None
    source_lat: Optional[float] = None
    source_lng: Optional[float] = None
    destination_lat: Optional[float] = None
    destination_lng: Optional[float] = None
    date: Optional[str] = None
    time: Optional[str] = None
    available_seats: Optional[int] = None
    estimated_cost: Optional[float] = None
    pickup_point: Optional[str] = None
    event_tag: Optional[str] = None

class RideRequestCreate(BaseModel):
    ride_id: str
    is_urgent: bool = False

class RideRequestAction(BaseModel):
    action: str = Field(..., pattern="^(accept|reject)$")

class VerificationUpload(BaseModel):
    student_id_image: str

class VerificationAction(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    reason: Optional[str] = None

class ChatMessage(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)

class StartRideRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=4)

class SOSCreate(BaseModel):
    ride_request_id: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    message: Optional[str] = None

class SOSAction(BaseModel):
    action: str = Field(..., pattern="^(review|resolve)$")
    notes: Optional[str] = None

class RatingCreate(BaseModel):
    ride_request_id: str
    rating: int = Field(..., ge=1, le=5)
    feedback: Optional[str] = Field(None, max_length=500)

class EventTagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=200)

class EventTagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=200)
    is_active: Optional[bool] = None

class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    vehicle_model: Optional[str] = None
    vehicle_number: Optional[str] = None
    vehicle_color: Optional[str] = None
    branch: Optional[str] = None
    academic_year: Optional[str] = None

class ReportCreate(BaseModel):
    reported_user_id: Optional[str] = None
    ride_id: Optional[str] = None
    category: str = Field(..., pattern="^(safety|behavior|misuse|other)$")
    description: str = Field(..., min_length=10, max_length=1000)

class ReportAction(BaseModel):
    action: str = Field(..., pattern="^(warn|suspend|disable|dismiss)$")
    admin_notes: Optional[str] = Field(None, max_length=500)

class UserStatusUpdate(BaseModel):
    is_active: bool
    reason: Optional[str] = Field(None, max_length=500)

class PromoteUserRequest(BaseModel):
    confirm: bool = True

# Trust Level Thresholds
TRUST_THRESHOLDS = {
    "trusted": {"min_rating": 4.0, "min_rides": 5},
    "new_user": {"max_rides": 4},
    "needs_review": {"max_rating": 2.5}
}

def row_to_dict(row):
    """Convert sqlite3.Row to dictionary"""
    if row is None:
        return None
    return dict(row)

def calculate_trust_level(avg_rating: float, ride_count: int) -> dict:
    """Calculate trust level based on rating and ride count"""
    if ride_count < TRUST_THRESHOLDS["new_user"]["max_rides"]:
        return {"level": "new", "label": "New User", "color": "gray"}
    elif avg_rating and avg_rating < TRUST_THRESHOLDS["needs_review"]["max_rating"]:
        return {"level": "low", "label": "Needs Review", "color": "red"}
    elif avg_rating and avg_rating >= TRUST_THRESHOLDS["trusted"]["min_rating"] and ride_count >= TRUST_THRESHOLDS["trusted"]["min_rides"]:
        return {"level": "trusted", "label": "Trusted", "color": "green"}
    else:
        return {"level": "regular", "label": "Regular", "color": "blue"}

def get_user_rating_stats(user_id: int) -> dict:
    """Get aggregated rating statistics for a user"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT rating FROM ratings WHERE rated_user_id = ?", (user_id,))
    ratings = cursor.fetchall()
    conn.close()
    
    if not ratings:
        return {
            "average_rating": None,
            "total_ratings": 0,
            "rating_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        }
    
    total = len(ratings)
    sum_ratings = sum(r["rating"] for r in ratings)
    avg = round(sum_ratings / total, 2) if total > 0 else None
    
    distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in ratings:
        distribution[r["rating"]] = distribution.get(r["rating"], 0) + 1
    
    return {
        "average_rating": avg,
        "total_ratings": total,
        "rating_distribution": distribution
    }

def calculate_user_badges(user_id: int, ride_count: int = None) -> list:
    """Calculate earned badges for a user"""
    conn = get_db()
    cursor = conn.cursor()
    
    if ride_count is None:
        cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if user and user["role"] == "driver":
            cursor.execute("SELECT COUNT(*) as count FROM rides WHERE driver_id = ? AND status = 'completed'", (user_id,))
            result = cursor.fetchone()
            ride_count = result["count"] if result else 0
        else:
            cursor.execute("SELECT COUNT(*) as count FROM ride_requests WHERE rider_id = ? AND status = 'completed'", (user_id,))
            result = cursor.fetchone()
            ride_count = result["count"] if result else 0
    
    conn.close()
    
    co2_saved = ride_count * AVG_RIDE_DISTANCE_KM * CO2_PER_KM_SAVED
    
    badges = []
    for badge in BADGE_DEFINITIONS:
        earned = False
        if "threshold" in badge:
            earned = ride_count >= badge["threshold"]
        elif "threshold_co2" in badge:
            earned = co2_saved >= badge["threshold_co2"]
        
        if earned:
            badges.append({
                "id": badge["id"],
                "name": badge["name"],
                "description": badge["description"],
                "icon": badge["icon"],
                "earned": True
            })
    
    return badges

def calculate_user_stats(user_id: int, user_role: str) -> dict:
    """Calculate comprehensive user statistics"""
    conn = get_db()
    cursor = conn.cursor()
    
    rides_offered = 0
    rides_taken = 0
    
    if user_role == "driver":
        cursor.execute("SELECT COUNT(*) as count FROM rides WHERE driver_id = ? AND status = 'completed'", (user_id,))
        result = cursor.fetchone()
        rides_offered = result["count"] if result else 0
        
        cursor.execute("SELECT COUNT(*) as count FROM ride_requests WHERE rider_id = ? AND status = 'completed'", (user_id,))
        result = cursor.fetchone()
        rides_taken = result["count"] if result else 0
    else:
        cursor.execute("SELECT COUNT(*) as count FROM ride_requests WHERE rider_id = ? AND status = 'completed'", (user_id,))
        result = cursor.fetchone()
        rides_taken = result["count"] if result else 0
        
        cursor.execute("SELECT COUNT(*) as count FROM rides WHERE driver_id = ? AND status = 'completed'", (user_id,))
        result = cursor.fetchone()
        rides_offered = result["count"] if result else 0
    
    conn.close()
    
    total_rides = rides_offered + rides_taken
    total_distance_km = total_rides * AVG_RIDE_DISTANCE_KM
    total_co2_saved = total_distance_km * CO2_PER_KM_SAVED
    money_saved = total_rides * AVG_RIDE_DISTANCE_KM * COST_PER_KM_SOLO * 0.5
    
    return {
        "rides_offered": rides_offered,
        "rides_taken": rides_taken,
        "total_rides": total_rides,
        "total_distance_km": round(total_distance_km, 1),
        "total_co2_saved_kg": round(total_co2_saved, 2),
        "money_saved": round(money_saved, 0),
        "streak": {"current": 0, "longest": 0}
    }

def log_admin_action(admin_id: int, admin_name: str, action_type: str, target_type: str, target_id: str, details: dict = None):
    """Log an admin action for audit trail"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO audit_logs (admin_id, admin_name, action_type, target_type, target_id, details, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (admin_id, admin_name, action_type, target_type, target_id, json.dumps(details or {}), datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

# Helper functions
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def validate_email_domain(email: str) -> bool:
    return email.lower().endswith(ALLOWED_EMAIL_DOMAIN)

def generate_ride_pin() -> str:
    return str(random.randint(1000, 9999))

def estimate_ride_duration(source: str, destination: str) -> int:
    base_time = 20
    distance_factor = (len(source) + len(destination)) // 10
    return base_time + (distance_factor * 5)

def calculate_estimated_arrival(start_time_str: str, duration_minutes: int) -> str:
    try:
        start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
        eta = start_time + timedelta(minutes=duration_minutes)
        return eta.isoformat()
    except:
        return None

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        conn.close()
        
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        
        user_dict = row_to_dict(user)
        if user_dict.get("is_active") == 0 and not user_dict.get("is_admin"):
            raise HTTPException(status_code=403, detail="Your account has been disabled. Please contact support.")
        
        return user_dict
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def serialize_user(user: dict) -> dict:
    """Serialize user data for API response"""
    user_id = user["id"]
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Count completed rides
    if user.get("role") == "driver":
        cursor.execute("SELECT COUNT(*) as count FROM rides WHERE driver_id = ? AND status = 'completed'", (user_id,))
        result = cursor.fetchone()
        ride_count = result["count"] if result else 0
    else:
        cursor.execute("SELECT COUNT(*) as count FROM ride_requests WHERE rider_id = ? AND status = 'completed'", (user_id,))
        result = cursor.fetchone()
        ride_count = result["count"] if result else 0
    
    conn.close()
    
    rating_stats = get_user_rating_stats(user_id)
    trust_level = calculate_trust_level(rating_stats["average_rating"], ride_count)
    badges = calculate_user_badges(user_id, ride_count)
    
    result = {
        "id": str(user_id),
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "is_admin": bool(user.get("is_admin", 0)),
        "verification_status": user.get("verification_status", "unverified"),
        "rejection_reason": user.get("rejection_reason"),
        "verified_at": user.get("verified_at"),
        "ride_count": ride_count,
        "created_at": user.get("created_at", ""),
        "average_rating": rating_stats["average_rating"],
        "total_ratings": rating_stats["total_ratings"],
        "rating_distribution": rating_stats["rating_distribution"],
        "trust_level": trust_level,
        "branch": user.get("branch"),
        "academic_year": user.get("academic_year"),
        "badges": badges,
        "is_active": bool(user.get("is_active", 1)),
        "is_suspended": bool(user.get("is_suspended", 0)),
        "warning_count": user.get("warning_count", 0)
    }
    
    if user.get("role") == "driver":
        result["vehicle_model"] = user.get("vehicle_model")
        result["vehicle_number"] = user.get("vehicle_number")
        result["vehicle_color"] = user.get("vehicle_color")
    
    return result

def get_event_tag_name(tag_id) -> str:
    """Get event tag name from ID"""
    if not tag_id:
        return None
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM event_tags WHERE id = ?", (tag_id,))
    tag = cursor.fetchone()
    conn.close()
    return tag["name"] if tag else None

def get_branch_name(branch_id: str) -> str:
    if not branch_id:
        return None
    for branch in BRANCHES:
        if branch["id"] == branch_id:
            return branch["name"]
    return None

def get_academic_year_name(year_id: str) -> str:
    if not year_id:
        return None
    for year in ACADEMIC_YEARS:
        if year["id"] == year_id:
            return year["name"]
    return None

def serialize_ride(ride: dict) -> dict:
    """Serialize ride data for API response"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE id = ?", (ride["driver_id"],))
    driver = cursor.fetchone()
    driver = row_to_dict(driver) if driver else None
    
    driver_name = driver["name"] if driver else "Unknown"
    driver_verification_status = driver.get("verification_status", "unverified") if driver else "unverified"
    
    driver_rating_stats = get_user_rating_stats(ride["driver_id"])
    cursor.execute("SELECT COUNT(*) as count FROM rides WHERE driver_id = ? AND status = 'completed'", (ride["driver_id"],))
    result = cursor.fetchone()
    driver_completed_rides = result["count"] if result else 0
    driver_trust_level = calculate_trust_level(driver_rating_stats["average_rating"], driver_completed_rides)
    
    if ride.get("status") == "completed":
        cursor.execute("SELECT COUNT(*) as count FROM ride_requests WHERE ride_id = ? AND status IN ('accepted', 'ongoing', 'completed')", (ride["id"],))
    else:
        cursor.execute("SELECT COUNT(*) as count FROM ride_requests WHERE ride_id = ? AND status IN ('accepted', 'ongoing')", (ride["id"],))
    
    result = cursor.fetchone()
    accepted_requests = result["count"] if result else 0
    
    conn.close()
    
    seats_taken = accepted_requests
    seats_available = ride["available_seats"] - seats_taken
    cost_per_rider = ride["estimated_cost"] / (seats_taken + 1) if seats_taken > 0 else ride["estimated_cost"]
    
    pickup_point_id = ride.get("pickup_point")
    pickup_point_name = None
    if pickup_point_id:
        for pp in PICKUP_POINTS:
            if pp["id"] == pickup_point_id:
                pickup_point_name = pp["name"]
                break
    
    return {
        "id": str(ride["id"]),
        "driver_id": str(ride["driver_id"]),
        "driver_name": driver_name,
        "driver_verification_status": driver_verification_status,
        "driver_average_rating": driver_rating_stats["average_rating"],
        "driver_total_ratings": driver_rating_stats["total_ratings"],
        "driver_trust_level": driver_trust_level,
        "driver_completed_rides": driver_completed_rides,
        "source": ride["source"],
        "destination": ride["destination"],
        "source_lat": ride.get("source_lat"),
        "source_lng": ride.get("source_lng"),
        "destination_lat": ride.get("destination_lat"),
        "destination_lng": ride.get("destination_lng"),
        "date": ride["date"],
        "time": ride["time"],
        "available_seats": ride["available_seats"],
        "seats_available": seats_available,
        "seats_taken": seats_taken,
        "estimated_cost": ride["estimated_cost"],
        "cost_per_rider": round(cost_per_rider, 2),
        "status": ride["status"],
        "pickup_point": pickup_point_id,
        "pickup_point_name": pickup_point_name,
        "is_recurring": bool(ride.get("is_recurring", 0)),
        "recurrence_pattern": ride.get("recurrence_pattern"),
        "parent_ride_id": str(ride["parent_ride_id"]) if ride.get("parent_ride_id") else None,
        "event_tag": str(ride["event_tag"]) if ride.get("event_tag") else None,
        "event_tag_name": get_event_tag_name(ride.get("event_tag")),
        "driver_branch": driver.get("branch") if driver else None,
        "driver_branch_name": get_branch_name(driver.get("branch")) if driver else None,
        "driver_academic_year": driver.get("academic_year") if driver else None,
        "driver_academic_year_name": get_academic_year_name(driver.get("academic_year")) if driver else None,
        "created_at": ride.get("created_at", "")
    }

def serialize_ride_request(request: dict) -> dict:
    """Serialize ride request data for API response"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE id = ?", (request["rider_id"],))
    rider = cursor.fetchone()
    rider = row_to_dict(rider) if rider else None
    
    cursor.execute("SELECT * FROM rides WHERE id = ?", (request["ride_id"],))
    ride = cursor.fetchone()
    ride = row_to_dict(ride) if ride else None
    
    driver = None
    if ride:
        cursor.execute("SELECT * FROM users WHERE id = ?", (ride["driver_id"],))
        driver = cursor.fetchone()
        driver = row_to_dict(driver) if driver else None
    
    conn.close()
    
    estimated_arrival = None
    estimated_duration = None
    if request.get("ride_started_at") and ride:
        estimated_duration = estimate_ride_duration(ride["source"], ride["destination"])
        estimated_arrival = calculate_estimated_arrival(request["ride_started_at"], estimated_duration)
    
    pickup_point_name = None
    if ride and ride.get("pickup_point"):
        for pp in PICKUP_POINTS:
            if pp["id"] == ride["pickup_point"]:
                pickup_point_name = pp["name"]
                break
    
    return {
        "id": str(request["id"]),
        "ride_id": str(request["ride_id"]),
        "rider_id": str(request["rider_id"]),
        "rider_name": rider["name"] if rider else "Unknown",
        "rider_email": rider["email"] if rider else "Unknown",
        "rider_verification_status": rider.get("verification_status", "unverified") if rider else "unverified",
        "ride_source": ride["source"] if ride else "Unknown",
        "ride_destination": ride["destination"] if ride else "Unknown",
        "source_lat": ride.get("source_lat") if ride else None,
        "source_lng": ride.get("source_lng") if ride else None,
        "destination_lat": ride.get("destination_lat") if ride else None,
        "destination_lng": ride.get("destination_lng") if ride else None,
        "ride_date": ride["date"] if ride else "Unknown",
        "ride_time": ride["time"] if ride else "Unknown",
        "ride_estimated_cost": ride["estimated_cost"] if ride else 0,
        "status": request["status"],
        "ride_pin": request.get("ride_pin"),
        "ride_started_at": request.get("ride_started_at"),
        "driver_id": str(ride["driver_id"]) if ride else None,
        "driver_name": driver["name"] if driver else "Unknown",
        "driver_verification_status": driver.get("verification_status", "unverified") if driver else "unverified",
        "driver_vehicle_model": driver.get("vehicle_model") if driver else None,
        "driver_vehicle_number": driver.get("vehicle_number") if driver else None,
        "driver_vehicle_color": driver.get("vehicle_color") if driver else None,
        "estimated_arrival": estimated_arrival,
        "estimated_duration_minutes": estimated_duration,
        "reached_safely_at": request.get("reached_safely_at"),
        "completed_at": request.get("completed_at"),
        "is_urgent": bool(request.get("is_urgent", 0)),
        "pickup_point": ride.get("pickup_point") if ride else None,
        "pickup_point_name": pickup_point_name,
        "created_at": request.get("created_at", "")
    }

def serialize_chat_message(message: dict) -> dict:
    """Serialize chat message for API response"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (message["sender_id"],))
    sender = cursor.fetchone()
    sender = row_to_dict(sender) if sender else None
    conn.close()
    
    return {
        "id": str(message["id"]),
        "ride_request_id": str(message["ride_request_id"]),
        "sender_id": str(message["sender_id"]),
        "sender_name": sender["name"] if sender else "Unknown",
        "sender_role": sender["role"] if sender else "Unknown",
        "message": message["message"],
        "created_at": message.get("created_at", "")
    }

def serialize_sos_event(sos: dict) -> dict:
    """Serialize SOS event for API response"""
    conn = get_db()
    cursor = conn.cursor()
    
    ride_request = None
    if sos.get("ride_request_id"):
        cursor.execute("SELECT * FROM ride_requests WHERE id = ?", (sos["ride_request_id"],))
        ride_request = cursor.fetchone()
        ride_request = row_to_dict(ride_request) if ride_request else None
    
    triggered_by_user = None
    if sos.get("triggered_by"):
        cursor.execute("SELECT * FROM users WHERE id = ?", (sos["triggered_by"],))
        triggered_by_user = cursor.fetchone()
        triggered_by_user = row_to_dict(triggered_by_user) if triggered_by_user else None
    
    ride = None
    rider = None
    driver = None
    if ride_request:
        cursor.execute("SELECT * FROM rides WHERE id = ?", (ride_request["ride_id"],))
        ride = cursor.fetchone()
        ride = row_to_dict(ride) if ride else None
        
        cursor.execute("SELECT * FROM users WHERE id = ?", (ride_request["rider_id"],))
        rider = cursor.fetchone()
        rider = row_to_dict(rider) if rider else None
        
        if ride:
            cursor.execute("SELECT * FROM users WHERE id = ?", (ride["driver_id"],))
            driver = cursor.fetchone()
            driver = row_to_dict(driver) if driver else None
    
    conn.close()
    
    return {
        "id": str(sos["id"]),
        "ride_request_id": str(sos["ride_request_id"]) if sos.get("ride_request_id") else None,
        "triggered_by": str(sos["triggered_by"]) if sos.get("triggered_by") else None,
        "triggered_by_name": triggered_by_user["name"] if triggered_by_user else "Unknown",
        "triggered_by_role": triggered_by_user["role"] if triggered_by_user else "Unknown",
        "latitude": sos.get("latitude"),
        "longitude": sos.get("longitude"),
        "message": sos.get("message"),
        "status": sos.get("status", "active"),
        "admin_notes": sos.get("admin_notes"),
        "reviewed_at": sos.get("reviewed_at"),
        "resolved_at": sos.get("resolved_at"),
        "resolved_by": str(sos["resolved_by"]) if sos.get("resolved_by") else None,
        "created_at": sos.get("created_at", ""),
        "ride_source": ride["source"] if ride else "Unknown",
        "ride_destination": ride["destination"] if ride else "Unknown",
        "ride_date": ride["date"] if ride else "Unknown",
        "ride_time": ride["time"] if ride else "Unknown",
        "rider_name": rider["name"] if rider else "Unknown",
        "rider_email": rider["email"] if rider else "Unknown",
        "driver_name": driver["name"] if driver else "Unknown",
        "driver_email": driver["email"] if driver else "Unknown",
    }

# Seed admin user on startup
@app.on_event("startup")
async def seed_admin():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@rvce.edu.in")
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin@123")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (admin_email,))
    existing_admin = cursor.fetchone()
    
    if not existing_admin:
        cursor.execute("""
            INSERT INTO users (email, password, name, role, is_admin, verification_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (admin_email, get_password_hash(admin_password), "Admin", "admin", 1, "verified", datetime.now(timezone.utc).isoformat()))
        conn.commit()
        print(f"Admin user created: {admin_email}")
    else:
        print(f"Admin user already exists: {admin_email}")
    
    conn.close()

# Health check
@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "CampusPool API", "database": "SQLite"}

# Auth endpoints
@app.post("/api/auth/signup")
async def signup(user: UserSignup):
    if not validate_email_domain(user.email):
        raise HTTPException(status_code=400, detail=f"Only {ALLOWED_EMAIL_DOMAIN} emails are allowed")
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE email = ?", (user.email.lower(),))
    existing_user = cursor.fetchone()
    if existing_user:
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")
    
    cursor.execute("""
        INSERT INTO users (email, password, name, role, is_admin, verification_status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user.email.lower(), get_password_hash(user.password), user.name, user.role, 0, "unverified", datetime.now(timezone.utc).isoformat()))
    
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    token = create_access_token({"user_id": str(user_id)})
    
    return {
        "message": "User created successfully",
        "token": token,
        "user": {
            "id": str(user_id),
            "email": user.email.lower(),
            "name": user.name,
            "role": user.role,
            "is_admin": False,
            "verification_status": "unverified",
            "ride_count": 0
        }
    }

@app.post("/api/auth/login")
async def login(user: UserLogin):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (user.email.lower(),))
    db_user = cursor.fetchone()
    conn.close()
    
    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    db_user = row_to_dict(db_user)
    
    if not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if db_user.get("is_active") == 0:
        raise HTTPException(status_code=403, detail="Your account has been disabled. Please contact support.")
    
    token = create_access_token({"user_id": str(db_user["id"])})
    
    return {
        "message": "Login successful",
        "token": token,
        "user": serialize_user(db_user)
    }

@app.get("/api/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return {"user": serialize_user(current_user)}

# Profile endpoints
@app.get("/api/profile")
async def get_profile(current_user: dict = Depends(get_current_user)):
    return {"user": serialize_user(current_user)}

@app.put("/api/profile")
async def update_profile(profile: UserProfile, current_user: dict = Depends(get_current_user)):
    update_fields = []
    update_values = []
    
    if profile.name:
        update_fields.append("name = ?")
        update_values.append(profile.name)
    if profile.role and profile.role in ["rider", "driver"]:
        update_fields.append("role = ?")
        update_values.append(profile.role)
    if profile.vehicle_model is not None:
        update_fields.append("vehicle_model = ?")
        update_values.append(profile.vehicle_model)
    if profile.vehicle_number is not None:
        update_fields.append("vehicle_number = ?")
        update_values.append(profile.vehicle_number)
    if profile.vehicle_color is not None:
        update_fields.append("vehicle_color = ?")
        update_values.append(profile.vehicle_color)
    
    if update_fields:
        update_values.append(current_user["id"])
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE users SET {', '.join(update_fields)} WHERE id = ?", update_values)
        conn.commit()
        
        cursor.execute("SELECT * FROM users WHERE id = ?", (current_user["id"],))
        updated_user = cursor.fetchone()
        conn.close()
        
        return {"message": "Profile updated", "user": serialize_user(row_to_dict(updated_user))}
    
    return {"message": "No changes made", "user": serialize_user(current_user)}

# Ride endpoints
@app.post("/api/rides")
async def create_ride(ride: RideCreate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can post rides")
    
    if current_user.get("verification_status") != "verified":
        raise HTTPException(status_code=403, detail="Only verified users can post rides. Please complete ID verification first.")
    
    if ride.pickup_point:
        valid_pickup_ids = [pp["id"] for pp in PICKUP_POINTS]
        if ride.pickup_point not in valid_pickup_ids:
            raise HTTPException(status_code=400, detail="Invalid pickup point")
    
    if ride.is_recurring:
        if not ride.recurrence_pattern:
            raise HTTPException(status_code=400, detail="Recurrence pattern is required for recurring rides")
        if not ride.recurrence_days_ahead:
            raise HTTPException(status_code=400, detail="Number of days ahead is required for recurring rides")
        
        valid_patterns = [p["id"] for p in RECURRENCE_PATTERNS]
        if ride.recurrence_pattern not in valid_patterns:
            raise HTTPException(status_code=400, detail="Invalid recurrence pattern")
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Handle event_tag conversion
    event_tag_id = None
    if ride.event_tag:
        try:
            event_tag_id = int(ride.event_tag)
        except ValueError:
            pass
    
    cursor.execute("""
        INSERT INTO rides (driver_id, source, destination, source_lat, source_lng, destination_lat, destination_lng,
                          date, time, available_seats, estimated_cost, status, pickup_point, is_recurring,
                          recurrence_pattern, event_tag, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (current_user["id"], ride.source, ride.destination, ride.source_lat, ride.source_lng,
          ride.destination_lat, ride.destination_lng, ride.date, ride.time, ride.available_seats,
          ride.estimated_cost, "active", ride.pickup_point, 1 if ride.is_recurring else 0,
          ride.recurrence_pattern if ride.is_recurring else None, event_tag_id,
          datetime.now(timezone.utc).isoformat()))
    
    ride_id = cursor.lastrowid
    conn.commit()
    
    cursor.execute("SELECT * FROM rides WHERE id = ?", (ride_id,))
    new_ride = cursor.fetchone()
    new_ride = row_to_dict(new_ride)
    
    created_rides = [serialize_ride(new_ride)]
    
    # Create recurring ride instances
    if ride.is_recurring and ride.recurrence_pattern and ride.recurrence_days_ahead:
        pattern = next((p for p in RECURRENCE_PATTERNS if p["id"] == ride.recurrence_pattern), None)
        if pattern:
            try:
                base_date = datetime.strptime(ride.date, "%Y-%m-%d")
                for day_offset in range(1, ride.recurrence_days_ahead + 1):
                    future_date = base_date + timedelta(days=day_offset)
                    if future_date.weekday() in pattern["days"]:
                        cursor.execute("""
                            SELECT * FROM rides WHERE driver_id = ? AND source = ? AND destination = ? AND date = ? AND time = ?
                        """, (current_user["id"], ride.source, ride.destination, future_date.strftime("%Y-%m-%d"), ride.time))
                        existing = cursor.fetchone()
                        
                        if not existing:
                            cursor.execute("""
                                INSERT INTO rides (driver_id, source, destination, source_lat, source_lng, destination_lat, destination_lng,
                                                  date, time, available_seats, estimated_cost, status, pickup_point, is_recurring,
                                                  parent_ride_id, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (current_user["id"], ride.source, ride.destination, ride.source_lat, ride.source_lng,
                                  ride.destination_lat, ride.destination_lng, future_date.strftime("%Y-%m-%d"), ride.time,
                                  ride.available_seats, ride.estimated_cost, "active", ride.pickup_point, 0, ride_id,
                                  datetime.now(timezone.utc).isoformat()))
                            
                            recurring_id = cursor.lastrowid
                            cursor.execute("SELECT * FROM rides WHERE id = ?", (recurring_id,))
                            recurring_ride = cursor.fetchone()
                            created_rides.append(serialize_ride(row_to_dict(recurring_ride)))
            except ValueError:
                pass
    
    conn.commit()
    conn.close()
    
    return {
        "message": f"Ride created successfully{' with ' + str(len(created_rides) - 1) + ' recurring instances' if len(created_rides) > 1 else ''}",
        "ride": created_rides[0],
        "recurring_rides_created": len(created_rides) - 1
    }

@app.get("/api/rides")
async def get_rides(
    destination: Optional[str] = None,
    source: Optional[str] = None,
    date: Optional[str] = None,
    pickup_point: Optional[str] = None,
    event_tag: Optional[str] = None,
    branch: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    conn = get_db()
    cursor = conn.cursor()
    
    query = "SELECT * FROM rides WHERE status = 'active'"
    params = []
    
    if destination:
        query += " AND LOWER(destination) LIKE ?"
        params.append(f"%{destination.lower()}%")
    if source:
        query += " AND LOWER(source) LIKE ?"
        params.append(f"%{source.lower()}%")
    if date:
        query += " AND date = ?"
        params.append(date)
    if pickup_point:
        query += " AND pickup_point = ?"
        params.append(pickup_point)
    if event_tag:
        query += " AND event_tag = ?"
        params.append(int(event_tag))
    
    query += " ORDER BY date ASC, time ASC"
    
    cursor.execute(query, params)
    rides = cursor.fetchall()
    conn.close()
    
    return {"rides": [serialize_ride(row_to_dict(r)) for r in rides]}

@app.get("/api/rides/my-rides")
async def get_my_rides(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM rides WHERE driver_id = ? ORDER BY date DESC, time DESC", (current_user["id"],))
    rides = cursor.fetchall()
    conn.close()
    return {"rides": [serialize_ride(row_to_dict(r)) for r in rides]}

@app.get("/api/rides/{ride_id}")
async def get_ride(ride_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM rides WHERE id = ?", (int(ride_id),))
    ride = cursor.fetchone()
    conn.close()
    
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    return {"ride": serialize_ride(row_to_dict(ride))}

@app.put("/api/rides/{ride_id}")
async def update_ride(ride_id: str, ride: RideUpdate, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM rides WHERE id = ?", (int(ride_id),))
    existing_ride = cursor.fetchone()
    
    if not existing_ride:
        conn.close()
        raise HTTPException(status_code=404, detail="Ride not found")
    
    existing_ride = row_to_dict(existing_ride)
    
    if existing_ride["driver_id"] != current_user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="You can only edit your own rides")
    
    update_fields = []
    update_values = []
    
    if ride.source is not None:
        update_fields.append("source = ?")
        update_values.append(ride.source)
    if ride.destination is not None:
        update_fields.append("destination = ?")
        update_values.append(ride.destination)
    if ride.source_lat is not None:
        update_fields.append("source_lat = ?")
        update_values.append(ride.source_lat)
    if ride.source_lng is not None:
        update_fields.append("source_lng = ?")
        update_values.append(ride.source_lng)
    if ride.destination_lat is not None:
        update_fields.append("destination_lat = ?")
        update_values.append(ride.destination_lat)
    if ride.destination_lng is not None:
        update_fields.append("destination_lng = ?")
        update_values.append(ride.destination_lng)
    if ride.date is not None:
        update_fields.append("date = ?")
        update_values.append(ride.date)
    if ride.time is not None:
        update_fields.append("time = ?")
        update_values.append(ride.time)
    if ride.available_seats is not None:
        update_fields.append("available_seats = ?")
        update_values.append(ride.available_seats)
    if ride.estimated_cost is not None:
        update_fields.append("estimated_cost = ?")
        update_values.append(ride.estimated_cost)
    if ride.pickup_point is not None:
        update_fields.append("pickup_point = ?")
        update_values.append(ride.pickup_point)
    if ride.event_tag is not None:
        update_fields.append("event_tag = ?")
        update_values.append(int(ride.event_tag) if ride.event_tag else None)
    
    if update_fields:
        update_values.append(int(ride_id))
        cursor.execute(f"UPDATE rides SET {', '.join(update_fields)} WHERE id = ?", update_values)
        conn.commit()
    
    cursor.execute("SELECT * FROM rides WHERE id = ?", (int(ride_id),))
    updated_ride = cursor.fetchone()
    conn.close()
    
    return {"message": "Ride updated", "ride": serialize_ride(row_to_dict(updated_ride))}

@app.delete("/api/rides/{ride_id}")
async def delete_ride(ride_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM rides WHERE id = ?", (int(ride_id),))
    ride = cursor.fetchone()
    
    if not ride:
        conn.close()
        raise HTTPException(status_code=404, detail="Ride not found")
    
    ride = row_to_dict(ride)
    
    if ride["driver_id"] != current_user["id"] and not current_user.get("is_admin"):
        conn.close()
        raise HTTPException(status_code=403, detail="You can only delete your own rides")
    
    cursor.execute("UPDATE rides SET status = 'cancelled' WHERE id = ?", (int(ride_id),))
    cursor.execute("UPDATE ride_requests SET status = 'cancelled' WHERE ride_id = ? AND status IN ('pending', 'accepted')", (int(ride_id),))
    conn.commit()
    conn.close()
    
    return {"message": "Ride cancelled successfully"}

# Ride Request endpoints
@app.post("/api/ride-requests")
async def create_ride_request(request: RideRequestCreate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "rider":
        raise HTTPException(status_code=403, detail="Only riders can request rides")
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM rides WHERE id = ?", (int(request.ride_id),))
    ride = cursor.fetchone()
    
    if not ride:
        conn.close()
        raise HTTPException(status_code=404, detail="Ride not found")
    
    ride = row_to_dict(ride)
    
    if ride["status"] != "active":
        conn.close()
        raise HTTPException(status_code=400, detail="This ride is no longer active")
    
    cursor.execute("SELECT * FROM ride_requests WHERE ride_id = ? AND rider_id = ?", (int(request.ride_id), current_user["id"]))
    existing_request = cursor.fetchone()
    
    if existing_request:
        conn.close()
        raise HTTPException(status_code=400, detail="You have already requested this ride")
    
    cursor.execute("SELECT COUNT(*) as count FROM ride_requests WHERE ride_id = ? AND status IN ('accepted', 'ongoing')", (int(request.ride_id),))
    result = cursor.fetchone()
    accepted_count = result["count"] if result else 0
    
    if accepted_count >= ride["available_seats"]:
        conn.close()
        raise HTTPException(status_code=400, detail="No seats available")
    
    cursor.execute("""
        INSERT INTO ride_requests (ride_id, rider_id, status, is_urgent, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (int(request.ride_id), current_user["id"], "pending", 1 if request.is_urgent else 0, datetime.now(timezone.utc).isoformat()))
    
    request_id = cursor.lastrowid
    conn.commit()
    
    cursor.execute("SELECT * FROM ride_requests WHERE id = ?", (request_id,))
    new_request = cursor.fetchone()
    conn.close()
    
    return {"message": "Ride request created", "request": serialize_ride_request(row_to_dict(new_request))}

@app.get("/api/ride-requests")
async def get_ride_requests(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ride_requests WHERE rider_id = ? ORDER BY created_at DESC", (current_user["id"],))
    requests = cursor.fetchall()
    conn.close()
    return {"requests": [serialize_ride_request(row_to_dict(r)) for r in requests]}

@app.get("/api/ride-requests/driver")
async def get_driver_requests(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can access this endpoint")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT rr.* FROM ride_requests rr
        JOIN rides r ON rr.ride_id = r.id
        WHERE r.driver_id = ?
        ORDER BY rr.created_at DESC
    """, (current_user["id"],))
    requests = cursor.fetchall()
    conn.close()
    return {"requests": [serialize_ride_request(row_to_dict(r)) for r in requests]}

@app.put("/api/ride-requests/{request_id}/action")
async def handle_ride_request(request_id: str, action: RideRequestAction, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM ride_requests WHERE id = ?", (int(request_id),))
    ride_request = cursor.fetchone()
    
    if not ride_request:
        conn.close()
        raise HTTPException(status_code=404, detail="Request not found")
    
    ride_request = row_to_dict(ride_request)
    
    cursor.execute("SELECT * FROM rides WHERE id = ?", (ride_request["ride_id"],))
    ride = cursor.fetchone()
    ride = row_to_dict(ride)
    
    if ride["driver_id"] != current_user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="Only the ride driver can handle requests")
    
    if ride_request["status"] != "pending":
        conn.close()
        raise HTTPException(status_code=400, detail="This request has already been handled")
    
    new_status = "accepted" if action.action == "accept" else "rejected"
    
    if action.action == "accept":
        cursor.execute("SELECT COUNT(*) as count FROM ride_requests WHERE ride_id = ? AND status IN ('accepted', 'ongoing')", (ride_request["ride_id"],))
        result = cursor.fetchone()
        accepted_count = result["count"] if result else 0
        
        if accepted_count >= ride["available_seats"]:
            conn.close()
            raise HTTPException(status_code=400, detail="No seats available")
        
        ride_pin = generate_ride_pin()
        cursor.execute("UPDATE ride_requests SET status = ?, ride_pin = ? WHERE id = ?", (new_status, ride_pin, int(request_id)))
    else:
        cursor.execute("UPDATE ride_requests SET status = ? WHERE id = ?", (new_status, int(request_id)))
    
    conn.commit()
    
    cursor.execute("SELECT * FROM ride_requests WHERE id = ?", (int(request_id),))
    updated_request = cursor.fetchone()
    conn.close()
    
    return {"message": f"Request {action.action}ed", "request": serialize_ride_request(row_to_dict(updated_request))}

@app.post("/api/ride-requests/{request_id}/start")
async def start_ride(request_id: str, start_data: StartRideRequest, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM ride_requests WHERE id = ?", (int(request_id),))
    ride_request = cursor.fetchone()
    
    if not ride_request:
        conn.close()
        raise HTTPException(status_code=404, detail="Request not found")
    
    ride_request = row_to_dict(ride_request)
    
    cursor.execute("SELECT * FROM rides WHERE id = ?", (ride_request["ride_id"],))
    ride = cursor.fetchone()
    ride = row_to_dict(ride)
    
    if ride["driver_id"] != current_user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="Only the driver can start the ride")
    
    if ride_request["status"] != "accepted":
        conn.close()
        raise HTTPException(status_code=400, detail="This request must be accepted first")
    
    if ride_request.get("ride_pin") != start_data.pin:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid PIN")
    
    cursor.execute("UPDATE ride_requests SET status = 'ongoing', ride_started_at = ? WHERE id = ?",
                   (datetime.now(timezone.utc).isoformat(), int(request_id)))
    conn.commit()
    
    cursor.execute("SELECT * FROM ride_requests WHERE id = ?", (int(request_id),))
    updated_request = cursor.fetchone()
    conn.close()
    
    return {"message": "Ride started", "request": serialize_ride_request(row_to_dict(updated_request))}

@app.post("/api/ride-requests/{request_id}/reached-safely")
async def reached_safely(request_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM ride_requests WHERE id = ?", (int(request_id),))
    ride_request = cursor.fetchone()
    
    if not ride_request:
        conn.close()
        raise HTTPException(status_code=404, detail="Request not found")
    
    ride_request = row_to_dict(ride_request)
    
    if ride_request["rider_id"] != current_user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="Only the rider can mark as reached safely")
    
    if ride_request["status"] != "ongoing":
        conn.close()
        raise HTTPException(status_code=400, detail="Ride must be ongoing")
    
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute("UPDATE ride_requests SET status = 'completed', reached_safely_at = ?, completed_at = ? WHERE id = ?",
                   (now, now, int(request_id)))
    
    # Check if all ride requests are completed
    cursor.execute("SELECT * FROM rides WHERE id = ?", (ride_request["ride_id"],))
    ride = cursor.fetchone()
    ride = row_to_dict(ride)
    
    cursor.execute("SELECT COUNT(*) as count FROM ride_requests WHERE ride_id = ? AND status = 'ongoing'", (ride_request["ride_id"],))
    result = cursor.fetchone()
    ongoing_count = result["count"] if result else 0
    
    if ongoing_count == 0:
        cursor.execute("UPDATE rides SET status = 'completed' WHERE id = ?", (ride_request["ride_id"],))
    
    conn.commit()
    
    cursor.execute("SELECT * FROM ride_requests WHERE id = ?", (int(request_id),))
    updated_request = cursor.fetchone()
    conn.close()
    
    return {"message": "Ride completed safely", "request": serialize_ride_request(row_to_dict(updated_request))}

@app.get("/api/ride-requests/{request_id}/live")
async def get_live_ride(request_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM ride_requests WHERE id = ?", (int(request_id),))
    ride_request = cursor.fetchone()
    
    if not ride_request:
        conn.close()
        raise HTTPException(status_code=404, detail="Request not found")
    
    ride_request = row_to_dict(ride_request)
    
    cursor.execute("SELECT * FROM rides WHERE id = ?", (ride_request["ride_id"],))
    ride = cursor.fetchone()
    ride = row_to_dict(ride)
    
    if ride_request["rider_id"] != current_user["id"] and ride["driver_id"] != current_user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="Access denied")
    
    cursor.execute("SELECT COUNT(*) as count FROM sos_events WHERE ride_request_id = ? AND status = 'active'", (int(request_id),))
    result = cursor.fetchone()
    has_active_sos = result["count"] > 0 if result else False
    
    conn.close()
    
    live_data = serialize_ride_request(ride_request)
    live_data["has_active_sos"] = has_active_sos
    
    return {"ride": live_data}

# Chat endpoints
@app.get("/api/chat/{request_id}/messages")
async def get_chat_messages(request_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM ride_requests WHERE id = ?", (int(request_id),))
    ride_request = cursor.fetchone()
    
    if not ride_request:
        conn.close()
        raise HTTPException(status_code=404, detail="Request not found")
    
    ride_request = row_to_dict(ride_request)
    
    cursor.execute("SELECT * FROM rides WHERE id = ?", (ride_request["ride_id"],))
    ride = cursor.fetchone()
    ride = row_to_dict(ride)
    
    if ride_request["rider_id"] != current_user["id"] and ride["driver_id"] != current_user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="Access denied")
    
    chat_enabled = ride_request["status"] in ["accepted", "ongoing"]
    
    cursor.execute("SELECT * FROM chat_messages WHERE ride_request_id = ? ORDER BY created_at ASC", (int(request_id),))
    messages = cursor.fetchall()
    conn.close()
    
    return {
        "messages": [serialize_chat_message(row_to_dict(m)) for m in messages],
        "chat_enabled": chat_enabled
    }

@app.post("/api/chat/{request_id}/messages")
async def send_chat_message(request_id: str, message: ChatMessage, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM ride_requests WHERE id = ?", (int(request_id),))
    ride_request = cursor.fetchone()
    
    if not ride_request:
        conn.close()
        raise HTTPException(status_code=404, detail="Request not found")
    
    ride_request = row_to_dict(ride_request)
    
    cursor.execute("SELECT * FROM rides WHERE id = ?", (ride_request["ride_id"],))
    ride = cursor.fetchone()
    ride = row_to_dict(ride)
    
    if ride_request["rider_id"] != current_user["id"] and ride["driver_id"] != current_user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="Access denied")
    
    if ride_request["status"] not in ["accepted", "ongoing"]:
        conn.close()
        raise HTTPException(status_code=400, detail="Chat is only available after request is accepted")
    
    cursor.execute("""
        INSERT INTO chat_messages (ride_request_id, sender_id, message, created_at)
        VALUES (?, ?, ?, ?)
    """, (int(request_id), current_user["id"], message.message, datetime.now(timezone.utc).isoformat()))
    
    message_id = cursor.lastrowid
    conn.commit()
    
    cursor.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,))
    new_message = cursor.fetchone()
    conn.close()
    
    return {"message": "Message sent", "chat_message": serialize_chat_message(row_to_dict(new_message))}

# SOS endpoints
@app.post("/api/sos")
async def create_sos(sos: SOSCreate, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM ride_requests WHERE id = ?", (int(sos.ride_request_id),))
    ride_request = cursor.fetchone()
    
    if not ride_request:
        conn.close()
        raise HTTPException(status_code=404, detail="Ride request not found")
    
    ride_request = row_to_dict(ride_request)
    
    cursor.execute("SELECT * FROM rides WHERE id = ?", (ride_request["ride_id"],))
    ride = cursor.fetchone()
    ride = row_to_dict(ride)
    
    if ride_request["rider_id"] != current_user["id"] and ride["driver_id"] != current_user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="Access denied")
    
    cursor.execute("""
        INSERT INTO sos_events (ride_request_id, triggered_by, latitude, longitude, message, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (int(sos.ride_request_id), current_user["id"], sos.latitude, sos.longitude, sos.message, "active",
          datetime.now(timezone.utc).isoformat()))
    
    sos_id = cursor.lastrowid
    conn.commit()
    
    cursor.execute("SELECT * FROM sos_events WHERE id = ?", (sos_id,))
    new_sos = cursor.fetchone()
    conn.close()
    
    return {"message": "SOS alert created", "sos": serialize_sos_event(row_to_dict(new_sos))}

@app.get("/api/sos")
async def get_sos_events(current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sos_events ORDER BY created_at DESC")
    events = cursor.fetchall()
    conn.close()
    
    return {"sos_events": [serialize_sos_event(row_to_dict(e)) for e in events]}

@app.put("/api/sos/{sos_id}/action")
async def handle_sos(sos_id: str, action: SOSAction, current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM sos_events WHERE id = ?", (int(sos_id),))
    sos = cursor.fetchone()
    
    if not sos:
        conn.close()
        raise HTTPException(status_code=404, detail="SOS event not found")
    
    now = datetime.now(timezone.utc).isoformat()
    
    if action.action == "review":
        cursor.execute("UPDATE sos_events SET status = 'reviewing', admin_notes = ?, reviewed_at = ? WHERE id = ?",
                       (action.notes, now, int(sos_id)))
    else:
        cursor.execute("UPDATE sos_events SET status = 'resolved', admin_notes = ?, resolved_at = ?, resolved_by = ? WHERE id = ?",
                       (action.notes, now, current_user["id"], int(sos_id)))
    
    conn.commit()
    
    cursor.execute("SELECT * FROM sos_events WHERE id = ?", (int(sos_id),))
    updated_sos = cursor.fetchone()
    conn.close()
    
    log_admin_action(current_user["id"], current_user["name"], f"sos_{action.action}", "sos", sos_id, {"notes": action.notes})
    
    return {"message": f"SOS {action.action}ed", "sos": serialize_sos_event(row_to_dict(updated_sos))}

# Rating endpoints
@app.post("/api/ratings")
async def create_rating(rating: RatingCreate, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM ride_requests WHERE id = ?", (int(rating.ride_request_id),))
    ride_request = cursor.fetchone()
    
    if not ride_request:
        conn.close()
        raise HTTPException(status_code=404, detail="Ride request not found")
    
    ride_request = row_to_dict(ride_request)
    
    if ride_request["status"] != "completed":
        conn.close()
        raise HTTPException(status_code=400, detail="Can only rate completed rides")
    
    cursor.execute("SELECT * FROM rides WHERE id = ?", (ride_request["ride_id"],))
    ride = cursor.fetchone()
    ride = row_to_dict(ride)
    
    if ride_request["rider_id"] == current_user["id"]:
        rated_user_id = ride["driver_id"]
    elif ride["driver_id"] == current_user["id"]:
        rated_user_id = ride_request["rider_id"]
    else:
        conn.close()
        raise HTTPException(status_code=403, detail="You were not part of this ride")
    
    cursor.execute("SELECT * FROM ratings WHERE ride_request_id = ? AND rater_id = ?",
                   (int(rating.ride_request_id), current_user["id"]))
    existing_rating = cursor.fetchone()
    
    if existing_rating:
        conn.close()
        raise HTTPException(status_code=400, detail="You have already rated this ride")
    
    cursor.execute("""
        INSERT INTO ratings (ride_request_id, rater_id, rated_user_id, rating, feedback, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (int(rating.ride_request_id), current_user["id"], rated_user_id, rating.rating, rating.feedback,
          datetime.now(timezone.utc).isoformat()))
    
    conn.commit()
    conn.close()
    
    return {"message": "Rating submitted successfully"}

@app.get("/api/ratings/can-rate/{request_id}")
async def can_rate(request_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM ride_requests WHERE id = ?", (int(request_id),))
    ride_request = cursor.fetchone()
    
    if not ride_request:
        conn.close()
        raise HTTPException(status_code=404, detail="Ride request not found")
    
    ride_request = row_to_dict(ride_request)
    
    if ride_request["status"] != "completed":
        conn.close()
        return {"can_rate": False, "reason": "Ride not completed"}
    
    cursor.execute("SELECT * FROM rides WHERE id = ?", (ride_request["ride_id"],))
    ride = cursor.fetchone()
    ride = row_to_dict(ride)
    
    cursor.execute("SELECT * FROM ratings WHERE ride_request_id = ? AND rater_id = ?",
                   (int(request_id), current_user["id"]))
    existing_rating = cursor.fetchone()
    
    if existing_rating:
        conn.close()
        return {"can_rate": False, "reason": "Already rated"}
    
    if ride_request["rider_id"] == current_user["id"]:
        cursor.execute("SELECT name FROM users WHERE id = ?", (ride["driver_id"],))
        rated_user = cursor.fetchone()
        rated_role = "driver"
    elif ride["driver_id"] == current_user["id"]:
        cursor.execute("SELECT name FROM users WHERE id = ?", (ride_request["rider_id"],))
        rated_user = cursor.fetchone()
        rated_role = "rider"
    else:
        conn.close()
        return {"can_rate": False, "reason": "Not part of ride"}
    
    conn.close()
    
    return {
        "can_rate": True,
        "rated_user_name": rated_user["name"] if rated_user else "Unknown",
        "rated_role": rated_role
    }

# Verification endpoints
@app.post("/api/verification/upload")
async def upload_verification(data: VerificationUpload, current_user: dict = Depends(get_current_user)):
    if current_user.get("verification_status") == "verified":
        raise HTTPException(status_code=400, detail="Already verified")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET student_id_image = ?, verification_status = ? WHERE id = ?",
                   (data.student_id_image, "pending", current_user["id"]))
    conn.commit()
    conn.close()
    
    return {"message": "Verification submitted"}

@app.get("/api/verification/pending")
async def get_pending_verifications(current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE verification_status = 'pending'")
    users = cursor.fetchall()
    conn.close()
    
    return {"users": [serialize_user(row_to_dict(u)) for u in users]}

@app.put("/api/verification/{user_id}/action")
async def handle_verification(user_id: str, action: VerificationAction, current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE id = ?", (int(user_id),))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    
    if action.action == "approve":
        cursor.execute("UPDATE users SET verification_status = 'verified', verified_at = ?, rejection_reason = NULL WHERE id = ?",
                       (datetime.now(timezone.utc).isoformat(), int(user_id)))
    else:
        cursor.execute("UPDATE users SET verification_status = 'rejected', rejection_reason = ? WHERE id = ?",
                       (action.reason, int(user_id)))
    
    conn.commit()
    
    cursor.execute("SELECT * FROM users WHERE id = ?", (int(user_id),))
    updated_user = cursor.fetchone()
    conn.close()
    
    log_admin_action(current_user["id"], current_user["name"], f"verification_{action.action}", "user", user_id, {"reason": action.reason})
    
    return {"message": f"User {action.action}d", "user": serialize_user(row_to_dict(updated_user))}

# User profile endpoints
@app.get("/api/users/{user_id}/profile")
async def get_user_profile(user_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (int(user_id),))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    profile = serialize_user(row_to_dict(user))
    
    # Add mutual info
    mutual_info = {
        "same_branch": current_user.get("branch") == profile.get("branch") and current_user.get("branch") is not None,
        "same_year": current_user.get("academic_year") == profile.get("academic_year") and current_user.get("academic_year") is not None
    }
    profile["mutual_info"] = mutual_info
    profile["branch_name"] = get_branch_name(profile.get("branch"))
    profile["academic_year_name"] = get_academic_year_name(profile.get("academic_year"))
    
    return {"profile": profile}

@app.put("/api/users/profile/community")
async def update_community_profile(profile: UserProfileUpdate, current_user: dict = Depends(get_current_user)):
    update_fields = []
    update_values = []
    
    if profile.branch:
        valid_branches = [b["id"] for b in BRANCHES]
        if profile.branch not in valid_branches:
            raise HTTPException(status_code=400, detail="Invalid branch")
        update_fields.append("branch = ?")
        update_values.append(profile.branch)
    
    if profile.academic_year:
        valid_years = [y["id"] for y in ACADEMIC_YEARS]
        if profile.academic_year not in valid_years:
            raise HTTPException(status_code=400, detail="Invalid academic year")
        update_fields.append("academic_year = ?")
        update_values.append(profile.academic_year)
    
    if update_fields:
        update_values.append(current_user["id"])
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE users SET {', '.join(update_fields)} WHERE id = ?", update_values)
        conn.commit()
        
        cursor.execute("SELECT * FROM users WHERE id = ?", (current_user["id"],))
        updated_user = cursor.fetchone()
        conn.close()
        
        return {"message": "Profile updated", "user": serialize_user(row_to_dict(updated_user))}
    
    return {"message": "No changes made", "user": serialize_user(current_user)}

# Stats endpoints
@app.get("/api/users/stats")
async def get_user_stats(current_user: dict = Depends(get_current_user)):
    stats = calculate_user_stats(current_user["id"], current_user["role"])
    badges = calculate_user_badges(current_user["id"])
    
    return {
        "stats": stats,
        "badges": badges
    }

# Pickup points endpoint
@app.get("/api/pickup-points")
async def get_pickup_points():
    return {"pickup_points": PICKUP_POINTS}

# Recurrence patterns endpoint
@app.get("/api/recurrence-patterns")
async def get_recurrence_patterns():
    return {"patterns": RECURRENCE_PATTERNS}

# Branches and years endpoints
@app.get("/api/branches")
async def get_branches():
    return {"branches": BRANCHES}

@app.get("/api/academic-years")
async def get_academic_years():
    return {"years": ACADEMIC_YEARS}

# Event tags endpoints
@app.post("/api/event-tags")
async def create_event_tag(tag: EventTagCreate, current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO event_tags (name, description, is_active, created_by, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (tag.name, tag.description, 1, current_user["id"], datetime.now(timezone.utc).isoformat()))
    
    tag_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {"message": "Event tag created", "tag": {"id": str(tag_id), "name": tag.name, "description": tag.description}}

@app.get("/api/event-tags")
async def get_event_tags():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM event_tags WHERE is_active = 1")
    tags = cursor.fetchall()
    conn.close()
    
    return {"tags": [{"id": str(t["id"]), "name": t["name"], "description": t["description"]} for t in tags]}

# Reports endpoints
@app.post("/api/reports")
async def create_report(report: ReportCreate, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO reports (reporter_id, reported_user_id, ride_id, category, description, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (current_user["id"], int(report.reported_user_id) if report.reported_user_id else None,
          int(report.ride_id) if report.ride_id else None, report.category, report.description, "pending",
          datetime.now(timezone.utc).isoformat()))
    
    report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {"message": "Report submitted", "report_id": str(report_id)}

@app.get("/api/reports")
async def get_reports(current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reports ORDER BY created_at DESC")
    reports = cursor.fetchall()
    conn.close()
    
    return {"reports": [row_to_dict(r) for r in reports]}

# Admin endpoints
@app.get("/api/admin/users")
async def get_all_users(current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = cursor.fetchall()
    conn.close()
    
    return {"users": [serialize_user(row_to_dict(u)) for u in users]}

@app.get("/api/admin/stats")
async def get_admin_stats(current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as count FROM users")
    total_users = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM rides")
    total_rides = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM rides WHERE status = 'active'")
    active_rides = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM rides WHERE status = 'completed'")
    completed_rides = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM sos_events WHERE status = 'active'")
    active_sos = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE verification_status = 'pending'")
    pending_verifications = cursor.fetchone()["count"]
    
    conn.close()
    
    return {
        "total_users": total_users,
        "total_rides": total_rides,
        "active_rides": active_rides,
        "completed_rides": completed_rides,
        "active_sos": active_sos,
        "pending_verifications": pending_verifications
    }

@app.get("/api/admin/audit-logs")
async def get_audit_logs(current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 100")
    logs = cursor.fetchall()
    conn.close()
    
    return {"logs": [row_to_dict(l) for l in logs]}

@app.put("/api/admin/users/{user_id}/status")
async def update_user_status(user_id: str, status: UserStatusUpdate, current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if status.is_active else 0, int(user_id)))
    conn.commit()
    
    cursor.execute("SELECT * FROM users WHERE id = ?", (int(user_id),))
    updated_user = cursor.fetchone()
    conn.close()
    
    action = "enabled" if status.is_active else "disabled"
    log_admin_action(current_user["id"], current_user["name"], f"user_{action}", "user", user_id, {"reason": status.reason})
    
    return {"message": f"User {action}", "user": serialize_user(row_to_dict(updated_user))}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
