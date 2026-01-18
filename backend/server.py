from fastapi import FastAPI, HTTPException, Depends, status, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from motor.motor_asyncio import AsyncIOMotorClient
import bcrypt
import jwt
import os
import uuid
from contextlib import asynccontextmanager

# Environment variables
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
JWT_SECRET = os.environ.get('JWT_SECRET', 'campuspool_secret_key_2024')
JWT_ALGORITHM = 'HS256'

# Trust thresholds
TRUSTED_RATING_THRESHOLD = 4.5
TRUSTED_MIN_RIDES = 10
NEW_USER_MAX_RIDES = 3
LOW_RATING_THRESHOLD = 3.0

# Eco Impact Constants (per shared ride)
CO2_PER_KM_SOLO = 0.21  # kg CO2 per km for solo driving
CO2_SAVINGS_FACTOR = 0.5  # 50% reduction when sharing
AVERAGE_RIDE_DISTANCE_KM = 15  # Default distance if not specified
COST_PER_KM = 0.15  # Average cost per km

# Predefined pickup points for campus
PICKUP_POINTS = [
    "Main Gate",
    "Library Building",
    "Student Center",
    "Engineering Block",
    "Science Block",
    "Sports Complex",
    "Cafeteria",
    "Admin Building",
    "Hostel Area",
    "Parking Lot A",
    "Parking Lot B",
    "Bus Stop"
]

# Predefined event tags
EVENT_TAGS = [
    {"id": "exams", "name": "Exams", "icon": "📝", "color": "#ef4444"},
    {"id": "fest", "name": "College Fest", "icon": "🎉", "color": "#8b5cf6"},
    {"id": "seminar", "name": "Seminar", "icon": "🎤", "color": "#3b82f6"},
    {"id": "sports", "name": "Sports Event", "icon": "🏆", "color": "#22c55e"},
    {"id": "placement", "name": "Placement Drive", "icon": "💼", "color": "#f59e0b"},
    {"id": "workshop", "name": "Workshop", "icon": "🔧", "color": "#06b6d4"},
    {"id": "cultural", "name": "Cultural Event", "icon": "🎭", "color": "#ec4899"},
    {"id": "holiday", "name": "Holiday Trip", "icon": "🌴", "color": "#10b981"}
]

# Academic branches
ACADEMIC_BRANCHES = [
    "Computer Science",
    "Electronics",
    "Mechanical",
    "Civil",
    "Chemical",
    "Electrical",
    "Information Technology",
    "Biotechnology",
    "Aerospace",
    "Other"
]

# Academic years
ACADEMIC_YEARS = ["1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year", "Alumni"]

# Badge definitions
BADGE_DEFINITIONS = [
    {"id": "first_ride", "name": "First Ride", "description": "Completed your first ride", "icon": "🚗", "requirement": 1},
    {"id": "ride_5", "name": "Regular Rider", "description": "Completed 5 rides", "icon": "⭐", "requirement": 5},
    {"id": "ride_10", "name": "Frequent Traveler", "description": "Completed 10 rides", "icon": "🌟", "requirement": 10},
    {"id": "ride_25", "name": "Road Warrior", "description": "Completed 25 rides", "icon": "🏅", "requirement": 25},
    {"id": "ride_50", "name": "Campus Legend", "description": "Completed 50 rides", "icon": "🏆", "requirement": 50},
    {"id": "eco_warrior", "name": "Eco Warrior", "description": "Saved 50kg CO2", "icon": "🌱", "requirement": 50, "type": "eco"},
    {"id": "eco_champion", "name": "Eco Champion", "description": "Saved 100kg CO2", "icon": "🌍", "requirement": 100, "type": "eco"},
    {"id": "streak_7", "name": "Week Streak", "description": "7 day ride streak", "icon": "🔥", "requirement": 7, "type": "streak"},
    {"id": "streak_30", "name": "Month Streak", "description": "30 day ride streak", "icon": "💥", "requirement": 30, "type": "streak"},
    {"id": "money_saver", "name": "Money Saver", "description": "Saved $100 on rides", "icon": "💰", "requirement": 100, "type": "savings"}
]

# Report categories
REPORT_CATEGORIES = ["safety", "behavior", "misuse", "fraud", "other"]

# SOS Status types
SOS_STATUSES = ["active", "under_review", "resolved"]

# User action types for admin
ADMIN_ACTION_TYPES = ["warn", "suspend", "disable", "enable", "revoke_verification", "verify"]

# Database client
client = None
db = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, db
    client = AsyncIOMotorClient(MONGO_URL)
    db = client.campuspool
    # Create indexes
    await db.users.create_index("email", unique=True)
    await db.rides.create_index("status")
    await db.rides.create_index("departure_time")
    await db.rides.create_index("event_tag")
    await db.rides.create_index([("source", "text"), ("destination", "text")])
    await db.ride_requests.create_index("ride_id")
    await db.ride_requests.create_index("is_urgent")
    await db.ratings.create_index([("ride_id", 1), ("rater_id", 1)], unique=True)
    await db.ratings.create_index("rated_user_id")
    await db.safe_completions.create_index("ride_id")
    await db.user_streaks.create_index("user_id")
    await db.custom_events.create_index("created_by")
    # Admin specific indexes
    await db.admin_audit_logs.create_index("admin_id")
    await db.admin_audit_logs.create_index("created_at")
    await db.sos_events.create_index("ride_id")
    await db.sos_events.create_index("status")
    await db.reports.create_index("status")
    await db.reports.create_index("category")
    await db.user_verifications.create_index("user_id")
    print("Database connected and indexes created")
    yield
    client.close()
    print("Database connection closed")

app = FastAPI(title="CampusPool API", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Models
class UserSignup(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    name: str = Field(..., min_length=2)
    role: str = Field(..., pattern="^(rider|driver|admin)$")
    branch: Optional[str] = None
    academic_year: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    branch: Optional[str] = None
    academic_year: Optional[str] = None

class RideCreate(BaseModel):
    source: str = Field(..., min_length=2)
    destination: str = Field(..., min_length=2)
    departure_time: datetime
    total_seats: int = Field(..., ge=1, le=8)
    estimated_cost: float = Field(..., ge=0)
    pickup_point: Optional[str] = None
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None
    event_tag: Optional[str] = None
    distance_km: Optional[float] = None

class RideSearch(BaseModel):
    source: Optional[str] = None
    destination: Optional[str] = None
    time_window_start: Optional[datetime] = None
    time_window_end: Optional[datetime] = None

class RideRequestCreate(BaseModel):
    ride_id: str
    is_urgent: bool = False

class RatingCreate(BaseModel):
    ride_id: str
    rated_user_id: str
    rating: int = Field(..., ge=1, le=5)
    feedback: Optional[str] = None

class SafeCompletionCreate(BaseModel):
    ride_id: str

class EventTagCreate(BaseModel):
    name: str = Field(..., min_length=2)
    icon: str = Field(default="📌")
    color: str = Field(default="#6b7280")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

# Admin-specific Pydantic Models
class SOSEventCreate(BaseModel):
    ride_id: str
    description: str = Field(..., min_length=5)
    location: Optional[str] = None

class SOSStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(active|under_review|resolved)$")
    admin_note: Optional[str] = None

class ReportCreate(BaseModel):
    target_type: str = Field(..., pattern="^(user|ride)$")
    target_id: str
    category: str = Field(..., pattern="^(safety|behavior|misuse|fraud|other)$")
    description: str = Field(..., min_length=10)

class ReportStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(pending|under_review|resolved|dismissed)$")
    action_taken: Optional[str] = None
    admin_note: Optional[str] = None

class UserActionRequest(BaseModel):
    action: str = Field(..., pattern="^(warn|suspend|disable|enable)$")
    reason: Optional[str] = None

class VerificationRequest(BaseModel):
    action: str = Field(..., pattern="^(verify|revoke)$")
    reason: Optional[str] = None

# Helper functions
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(user_id: str) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization token required")
    
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload["user_id"]})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        # Check if user is disabled
        if user.get("is_disabled", False):
            raise HTTPException(status_code=403, detail="Your account has been disabled. Contact support.")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_admin_user(authorization: Optional[str] = Header(None)):
    """Get current user and verify they have admin role"""
    user = await get_current_user(authorization)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

async def log_admin_action(admin_id: str, admin_name: str, action_type: str, target_type: str, 
                          target_id: str, details: str = None):
    """Log an admin action for audit purposes"""
    log_entry = {
        "id": str(uuid.uuid4()),
        "admin_id": admin_id,
        "admin_name": admin_name,
        "action_type": action_type,
        "target_type": target_type,
        "target_id": target_id,
        "details": details,
        "created_at": datetime.now(timezone.utc)
    }
    await db.admin_audit_logs.insert_one(log_entry)
    return log_entry

def calculate_route_similarity(ride_source: str, ride_dest: str, search_source: str, search_dest: str) -> int:
    """Calculate similarity score between ride route and search criteria"""
    score = 0
    
    if search_source:
        ride_source_lower = ride_source.lower()
        search_source_lower = search_source.lower()
        if search_source_lower in ride_source_lower or ride_source_lower in search_source_lower:
            score += 50
        elif any(word in ride_source_lower for word in search_source_lower.split()):
            score += 25
    
    if search_dest:
        ride_dest_lower = ride_dest.lower()
        search_dest_lower = search_dest.lower()
        if search_dest_lower in ride_dest_lower or ride_dest_lower in search_dest_lower:
            score += 50
        elif any(word in ride_dest_lower for word in search_dest_lower.split()):
            score += 25
    
    return score

async def generate_recurring_rides(ride_data: dict, user_id: str, pattern: str):
    """Generate future ride entries based on recurrence pattern"""
    base_time = ride_data["departure_time"]
    rides_to_create = []
    
    if pattern == "weekdays":
        for i in range(1, 15):
            next_date = base_time + timedelta(days=i)
            if next_date.weekday() < 5:
                new_ride = ride_data.copy()
                new_ride["id"] = str(uuid.uuid4())
                new_ride["departure_time"] = next_date
                new_ride["parent_ride_id"] = ride_data["id"]
                rides_to_create.append(new_ride)
    elif pattern == "daily":
        for i in range(1, 8):
            new_ride = ride_data.copy()
            new_ride["id"] = str(uuid.uuid4())
            new_ride["departure_time"] = base_time + timedelta(days=i)
            new_ride["parent_ride_id"] = ride_data["id"]
            rides_to_create.append(new_ride)
    elif pattern == "weekly":
        for i in range(1, 5):
            new_ride = ride_data.copy()
            new_ride["id"] = str(uuid.uuid4())
            new_ride["departure_time"] = base_time + timedelta(weeks=i)
            new_ride["parent_ride_id"] = ride_data["id"]
            rides_to_create.append(new_ride)
    
    if rides_to_create:
        await db.rides.insert_many(rides_to_create)
    
    return len(rides_to_create)

async def get_user_trust_info(user_id: str) -> dict:
    """Calculate trust information for a user"""
    driver_rides = await db.rides.count_documents({"driver_id": user_id, "status": "completed"})
    rider_requests = await db.ride_requests.count_documents({"rider_id": user_id, "status": "accepted"})
    total_rides = driver_rides + rider_requests
    
    pipeline = [
        {"$match": {"rated_user_id": user_id}},
        {"$group": {"_id": None, "avgRating": {"$avg": "$rating"}, "count": {"$sum": 1}}}
    ]
    rating_result = await db.ratings.aggregate(pipeline).to_list(1)
    
    avg_rating = 0
    rating_count = 0
    if rating_result:
        avg_rating = round(rating_result[0]["avgRating"], 1)
        rating_count = rating_result[0]["count"]
    
    trust_label = "new_user"
    if total_rides < NEW_USER_MAX_RIDES:
        trust_label = "new_user"
    elif rating_count > 0 and avg_rating < LOW_RATING_THRESHOLD:
        trust_label = "low_rating"
    elif total_rides >= TRUSTED_MIN_RIDES and avg_rating >= TRUSTED_RATING_THRESHOLD:
        trust_label = "trusted"
    elif total_rides >= NEW_USER_MAX_RIDES:
        trust_label = "regular"
    
    return {
        "totalRides": total_rides,
        "avgRating": avg_rating,
        "ratingCount": rating_count,
        "trustLabel": trust_label
    }

async def calculate_user_statistics(user_id: str) -> dict:
    """Calculate comprehensive statistics for a user"""
    user = await db.users.find_one({"id": user_id})
    if not user:
        return {}
    
    # Rides offered (as driver)
    rides_offered = await db.rides.count_documents({"driver_id": user_id, "status": "completed"})
    
    # Rides taken (as rider)
    rides_taken_cursor = db.ride_requests.find({"rider_id": user_id, "status": "accepted"})
    rides_taken_list = await rides_taken_cursor.to_list(1000)
    
    rides_taken = 0
    total_distance_as_rider = 0
    total_cost_as_rider = 0
    
    for req in rides_taken_list:
        ride = await db.rides.find_one({"id": req["ride_id"], "status": "completed"})
        if ride:
            rides_taken += 1
            distance = ride.get("distance_km", AVERAGE_RIDE_DISTANCE_KM)
            total_distance_as_rider += distance
            # Calculate shared cost
            accepted_count = await db.ride_requests.count_documents({"ride_id": ride["id"], "status": "accepted"})
            cost_per_rider = ride["estimated_cost"] / max(accepted_count, 1)
            total_cost_as_rider += cost_per_rider
    
    # Distance as driver
    driver_rides_cursor = db.rides.find({"driver_id": user_id, "status": "completed"})
    driver_rides_list = await driver_rides_cursor.to_list(1000)
    total_distance_as_driver = sum(r.get("distance_km", AVERAGE_RIDE_DISTANCE_KM) for r in driver_rides_list)
    
    total_distance = total_distance_as_rider + total_distance_as_driver
    
    # Money saved calculation (compared to solo travel)
    solo_cost = total_distance_as_rider * COST_PER_KM * 2  # Solo would cost more
    money_saved = max(0, solo_cost - total_cost_as_rider)
    
    # CO2 savings calculation
    co2_saved = total_distance * CO2_PER_KM_SOLO * CO2_SAVINGS_FACTOR
    
    return {
        "ridesOffered": rides_offered,
        "ridesTaken": rides_taken,
        "totalRides": rides_offered + rides_taken,
        "totalDistanceKm": round(total_distance, 1),
        "moneySaved": round(money_saved, 2),
        "co2SavedKg": round(co2_saved, 2)
    }

async def calculate_user_streak(user_id: str) -> dict:
    """Calculate ride streak for a user"""
    # Get all completed rides/requests for user in last 60 days
    sixty_days_ago = datetime.now(timezone.utc) - timedelta(days=60)
    
    # Get ride dates as driver
    driver_rides = await db.rides.find({
        "driver_id": user_id,
        "status": "completed",
        "departure_time": {"$gte": sixty_days_ago}
    }).to_list(1000)
    
    # Get ride dates as rider
    rider_requests = await db.ride_requests.find({
        "rider_id": user_id,
        "status": "accepted"
    }).to_list(1000)
    
    ride_dates = set()
    
    for ride in driver_rides:
        ride_dates.add(ride["departure_time"].date())
    
    for req in rider_requests:
        ride = await db.rides.find_one({"id": req["ride_id"], "status": "completed"})
        if ride and ride["departure_time"] >= sixty_days_ago:
            ride_dates.add(ride["departure_time"].date())
    
    if not ride_dates:
        return {"currentStreak": 0, "longestStreak": 0}
    
    sorted_dates = sorted(ride_dates, reverse=True)
    today = datetime.now(timezone.utc).date()
    
    # Calculate current streak
    current_streak = 0
    check_date = today
    
    for i in range(60):
        if check_date in sorted_dates:
            current_streak += 1
            check_date -= timedelta(days=1)
        elif i == 0:
            # If no ride today, check yesterday
            check_date -= timedelta(days=1)
            if check_date in sorted_dates:
                current_streak += 1
                check_date -= timedelta(days=1)
            else:
                break
        else:
            break
    
    # Calculate longest streak
    longest_streak = 0
    current_count = 1
    
    for i in range(1, len(sorted_dates)):
        diff = (sorted_dates[i-1] - sorted_dates[i]).days
        if diff == 1:
            current_count += 1
        else:
            longest_streak = max(longest_streak, current_count)
            current_count = 1
    
    longest_streak = max(longest_streak, current_count)
    
    return {
        "currentStreak": current_streak,
        "longestStreak": longest_streak
    }

async def get_user_badges(user_id: str) -> List[dict]:
    """Calculate earned badges for a user"""
    stats = await calculate_user_statistics(user_id)
    streak = await calculate_user_streak(user_id)
    
    earned_badges = []
    
    for badge in BADGE_DEFINITIONS:
        earned = False
        badge_type = badge.get("type", "rides")
        
        if badge_type == "eco":
            if stats.get("co2SavedKg", 0) >= badge["requirement"]:
                earned = True
        elif badge_type == "streak":
            if streak.get("longestStreak", 0) >= badge["requirement"]:
                earned = True
        elif badge_type == "savings":
            if stats.get("moneySaved", 0) >= badge["requirement"]:
                earned = True
        else:
            # Default: rides count
            if stats.get("totalRides", 0) >= badge["requirement"]:
                earned = True
        
        if earned:
            earned_badges.append({
                "id": badge["id"],
                "name": badge["name"],
                "description": badge["description"],
                "icon": badge["icon"],
                "earnedAt": datetime.now(timezone.utc).isoformat()
            })
    
    return earned_badges

async def get_weekly_summary(user_id: str) -> dict:
    """Get weekly summary for a user"""
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    
    # Rides as driver this week
    driver_rides = await db.rides.find({
        "driver_id": user_id,
        "status": "completed",
        "departure_time": {"$gte": seven_days_ago}
    }).to_list(100)
    
    # Rides as rider this week
    rider_requests = await db.ride_requests.find({
        "rider_id": user_id,
        "status": "accepted"
    }).to_list(100)
    
    weekly_rides_taken = 0
    weekly_distance = 0
    weekly_cost = 0
    
    for ride in driver_rides:
        weekly_distance += ride.get("distance_km", AVERAGE_RIDE_DISTANCE_KM)
    
    for req in rider_requests:
        ride = await db.rides.find_one({
            "id": req["ride_id"],
            "status": "completed",
            "departure_time": {"$gte": seven_days_ago}
        })
        if ride:
            weekly_rides_taken += 1
            weekly_distance += ride.get("distance_km", AVERAGE_RIDE_DISTANCE_KM)
            accepted_count = await db.ride_requests.count_documents({"ride_id": ride["id"], "status": "accepted"})
            weekly_cost += ride["estimated_cost"] / max(accepted_count, 1)
    
    weekly_rides_offered = len(driver_rides)
    solo_cost = weekly_distance * COST_PER_KM * 2
    weekly_money_saved = max(0, solo_cost - weekly_cost) if weekly_rides_taken > 0 else 0
    weekly_co2_saved = weekly_distance * CO2_PER_KM_SOLO * CO2_SAVINGS_FACTOR
    
    return {
        "ridesOffered": weekly_rides_offered,
        "ridesTaken": weekly_rides_taken,
        "totalRides": weekly_rides_offered + weekly_rides_taken,
        "distanceKm": round(weekly_distance, 1),
        "moneySaved": round(weekly_money_saved, 2),
        "co2SavedKg": round(weekly_co2_saved, 2),
        "periodStart": seven_days_ago.isoformat(),
        "periodEnd": datetime.now(timezone.utc).isoformat()
    }

# API Routes

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "CampusPool API"}

@app.get("/api/pickup-points")
async def get_pickup_points():
    return {"pickup_points": PICKUP_POINTS}

@app.get("/api/event-tags")
async def get_event_tags():
    """Get all available event tags"""
    # Get custom event tags from database
    custom_tags = await db.custom_events.find({}).to_list(100)
    custom_formatted = [
        {"id": t["id"], "name": t["name"], "icon": t["icon"], "color": t["color"]}
        for t in custom_tags
    ]
    return {"event_tags": EVENT_TAGS + custom_formatted}

@app.post("/api/event-tags")
async def create_event_tag(tag_data: EventTagCreate, user: dict = Depends(get_current_user)):
    """Create a custom event tag (admin only)"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create event tags")
    
    tag_id = str(uuid.uuid4())[:8]
    new_tag = {
        "id": tag_id,
        "name": tag_data.name,
        "icon": tag_data.icon,
        "color": tag_data.color,
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc)
    }
    
    await db.custom_events.insert_one(new_tag)
    
    # Log admin action
    await log_admin_action(
        user["id"], user["name"], "create_event_tag", "event_tag", tag_id,
        f"Created event tag: {tag_data.name}"
    )
    
    return {"message": "Event tag created", "tag": new_tag}

@app.get("/api/academic-options")
async def get_academic_options():
    """Get available branches and academic years"""
    return {
        "branches": ACADEMIC_BRANCHES,
        "academic_years": ACADEMIC_YEARS
    }

# Auth Routes
@app.post("/api/auth/signup", response_model=TokenResponse)
async def signup(user_data: UserSignup):
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    user = {
        "id": user_id,
        "email": user_data.email,
        "password_hash": hash_password(user_data.password),
        "name": user_data.name,
        "role": user_data.role,
        "branch": user_data.branch,
        "academic_year": user_data.academic_year,
        "is_verified": False,
        "is_disabled": False,
        "is_suspended": False,
        "warnings": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    
    await db.users.insert_one(user)
    token = create_token(user_id)
    
    return {
        "access_token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "branch": user.get("branch"),
            "academicYear": user.get("academic_year")
        }
    }

@app.post("/api/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email})
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Check if user is disabled
    if user.get("is_disabled", False):
        raise HTTPException(status_code=403, detail="Your account has been disabled. Contact support.")
    
    token = create_token(user["id"])
    
    return {
        "access_token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "branch": user.get("branch"),
            "academicYear": user.get("academic_year")
        }
    }

@app.get("/api/auth/me")
async def get_current_user_info(user: dict = Depends(get_current_user)):
    trust_info = await get_user_trust_info(user["id"])
    stats = await calculate_user_statistics(user["id"])
    streak = await calculate_user_streak(user["id"])
    badges = await get_user_badges(user["id"])
    
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "branch": user.get("branch"),
        "academicYear": user.get("academic_year"),
        "isVerified": user.get("is_verified", False),
        "isDisabled": user.get("is_disabled", False),
        "isSuspended": user.get("is_suspended", False),
        **trust_info,
        "statistics": stats,
        "streak": streak,
        "badges": badges
    }

@app.patch("/api/auth/profile")
async def update_profile(profile_data: UserProfileUpdate, user: dict = Depends(get_current_user)):
    """Update user profile"""
    update_fields = {}
    
    if profile_data.name:
        update_fields["name"] = profile_data.name
    if profile_data.branch:
        if profile_data.branch not in ACADEMIC_BRANCHES:
            raise HTTPException(status_code=400, detail="Invalid branch")
        update_fields["branch"] = profile_data.branch
    if profile_data.academic_year:
        if profile_data.academic_year not in ACADEMIC_YEARS:
            raise HTTPException(status_code=400, detail="Invalid academic year")
        update_fields["academic_year"] = profile_data.academic_year
    
    if update_fields:
        update_fields["updated_at"] = datetime.now(timezone.utc)
        await db.users.update_one({"id": user["id"]}, {"$set": update_fields})
    
    return {"message": "Profile updated successfully"}

# User Profile Routes
@app.get("/api/users/{user_id}/profile")
async def get_user_profile(user_id: str, current_user: dict = Depends(get_current_user)):
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    trust_info = await get_user_trust_info(user_id)
    badges = await get_user_badges(user_id)
    
    # Check for mutual academic details
    mutual_info = {}
    if current_user["id"] != user_id:
        if current_user.get("branch") and user.get("branch"):
            if current_user["branch"] == user["branch"]:
                mutual_info["sameBranch"] = True
        if current_user.get("academic_year") and user.get("academic_year"):
            if current_user["academic_year"] == user["academic_year"]:
                mutual_info["sameYear"] = True
    
    return {
        "id": user["id"],
        "name": user["name"],
        "role": user["role"],
        "branch": user.get("branch"),
        "academicYear": user.get("academic_year"),
        "isVerified": user.get("is_verified", False),
        "createdAt": user["created_at"].isoformat() if user.get("created_at") else None,
        **trust_info,
        "badges": badges[:5],  # Show top 5 badges
        "mutualInfo": mutual_info
    }

# Statistics Routes
@app.get("/api/users/me/statistics")
async def get_my_statistics(user: dict = Depends(get_current_user)):
    """Get detailed statistics for current user"""
    stats = await calculate_user_statistics(user["id"])
    streak = await calculate_user_streak(user["id"])
    weekly = await get_weekly_summary(user["id"])
    badges = await get_user_badges(user["id"])
    
    return {
        "statistics": stats,
        "streak": streak,
        "weeklySummary": weekly,
        "badges": badges
    }

@app.get("/api/users/me/weekly-summary")
async def get_my_weekly_summary(user: dict = Depends(get_current_user)):
    """Get weekly summary for current user"""
    return await get_weekly_summary(user["id"])

@app.get("/api/users/me/eco-impact")
async def get_my_eco_impact(user: dict = Depends(get_current_user)):
    """Get eco impact details for current user"""
    stats = await calculate_user_statistics(user["id"])
    
    co2_saved = stats.get("co2SavedKg", 0)
    total_distance = stats.get("totalDistanceKm", 0)
    
    # Calculate equivalents
    trees_equivalent = co2_saved / 21  # Average tree absorbs 21kg CO2/year
    gallons_saved = total_distance * 0.04  # Approximate gallons of gas saved
    
    return {
        "co2SavedKg": co2_saved,
        "totalDistanceKm": total_distance,
        "treesEquivalent": round(trees_equivalent, 1),
        "gallonsSaved": round(gallons_saved, 1),
        "ridesShared": stats.get("totalRides", 0)
    }

# Rides Routes
@app.post("/api/rides")
async def create_ride(ride_data: RideCreate, user: dict = Depends(get_current_user)):
    
    if user["role"] != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can post rides")
    
    if ride_data.pickup_point and ride_data.pickup_point not in PICKUP_POINTS:
        raise HTTPException(status_code=400, detail="Invalid pickup point")
    
    # Validate event tag if provided
    if ride_data.event_tag:
        valid_tags = [t["id"] for t in EVENT_TAGS]
        custom_tags = await db.custom_events.find({}).to_list(100)
        valid_tags.extend([t["id"] for t in custom_tags])
        if ride_data.event_tag not in valid_tags:
            raise HTTPException(status_code=400, detail="Invalid event tag")
    
    ride_id = str(uuid.uuid4())
    ride = {
        "id": ride_id,
        "driver_id": user["id"],
        "driver_name": user["name"],
        "driver_branch": user.get("branch"),
        "driver_year": user.get("academic_year"),
        "source": ride_data.source,
        "destination": ride_data.destination,
        "departure_time": ride_data.departure_time,
        "total_seats": ride_data.total_seats,
        "available_seats": ride_data.total_seats,
        "estimated_cost": ride_data.estimated_cost,
        "pickup_point": ride_data.pickup_point,
        "is_recurring": ride_data.is_recurring,
        "recurrence_pattern": ride_data.recurrence_pattern,
        "parent_ride_id": None,
        "event_tag": ride_data.event_tag,
        "distance_km": ride_data.distance_km or AVERAGE_RIDE_DISTANCE_KM,
        "status": "posted",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    
    await db.rides.insert_one(ride)
    
    recurring_count = 0
    if ride_data.is_recurring and ride_data.recurrence_pattern:
        recurring_count = await generate_recurring_rides(ride, user["id"], ride_data.recurrence_pattern)
    
    return {
        "message": "Ride posted successfully",
        "ride": ride,
        "recurring_rides_created": recurring_count
    }

@app.get("/api/rides")
async def get_rides(
    source: Optional[str] = None,
    destination: Optional[str] = None,
    time_window_start: Optional[str] = None,
    time_window_end: Optional[str] = None,
    event_tag: Optional[str] = None,
    branch: Optional[str] = None,
    academic_year: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
):
    query = {
        "status": "posted",
        "available_seats": {"$gt": 0},
        "departure_time": {"$gte": datetime.now(timezone.utc)}
    }
    
    if time_window_start:
        try:
            start_time = datetime.fromisoformat(time_window_start.replace('Z', '+00:00'))
            query["departure_time"]["$gte"] = start_time
        except:
            pass
    
    if time_window_end:
        try:
            end_time = datetime.fromisoformat(time_window_end.replace('Z', '+00:00'))
            query["departure_time"]["$lte"] = end_time
        except:
            pass
    
    # Event tag filter
    if event_tag:
        query["event_tag"] = event_tag
    
    # Community filters
    if branch:
        query["driver_branch"] = branch
    if academic_year:
        query["driver_year"] = academic_year
    
    cursor = db.rides.find(query).sort("departure_time", 1).skip(offset).limit(limit)
    rides = await cursor.to_list(length=limit)
    
    if source or destination:
        for ride in rides:
            ride["recommendation_score"] = calculate_route_similarity(
                ride["source"], ride["destination"],
                source or "", destination or ""
            )
        rides.sort(key=lambda x: (-x.get("recommendation_score", 0), x["departure_time"]))
    else:
        for ride in rides:
            ride["recommendation_score"] = 0
    
    # Get event tag info
    all_tags = {t["id"]: t for t in EVENT_TAGS}
    custom_tags = await db.custom_events.find({}).to_list(100)
    for t in custom_tags:
        all_tags[t["id"]] = t
    
    formatted_rides = []
    for ride in rides:
        occupied = ride["total_seats"] - ride["available_seats"]
        cost_per_rider = ride["estimated_cost"] / max(occupied, 1)
        
        driver_trust = await get_user_trust_info(ride["driver_id"])
        
        event_info = None
        if ride.get("event_tag"):
            tag_data = all_tags.get(ride["event_tag"])
            if tag_data:
                event_info = {
                    "id": tag_data["id"],
                    "name": tag_data["name"],
                    "icon": tag_data["icon"],
                    "color": tag_data["color"]
                }
        
        formatted_rides.append({
            "id": ride["id"],
            "driverId": ride["driver_id"],
            "driverName": ride["driver_name"],
            "driverBranch": ride.get("driver_branch"),
            "driverYear": ride.get("driver_year"),
            "driverTrust": driver_trust,
            "source": ride["source"],
            "destination": ride["destination"],
            "departureTime": ride["departure_time"].isoformat(),
            "totalSeats": ride["total_seats"],
            "availableSeats": ride["available_seats"],
            "estimatedCost": ride["estimated_cost"],
            "costPerRider": round(cost_per_rider, 2),
            "pickupPoint": ride.get("pickup_point"),
            "isRecurring": ride.get("is_recurring", False),
            "recurrencePattern": ride.get("recurrence_pattern"),
            "eventTag": event_info,
            "distanceKm": ride.get("distance_km", AVERAGE_RIDE_DISTANCE_KM),
            "status": ride["status"],
            "recommendationScore": ride.get("recommendation_score", 0),
            "isRecommended": ride.get("recommendation_score", 0) >= 25
        })
    
    return {
        "message": "Rides retrieved successfully",
        "rides": formatted_rides,
        "total": len(formatted_rides)
    }

@app.get("/api/rides/{ride_id}")
async def get_ride(ride_id: str):
    ride = await db.rides.find_one({"id": ride_id})
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    occupied = ride["total_seats"] - ride["available_seats"]
    cost_per_rider = ride["estimated_cost"] / max(occupied, 1)
    
    driver_trust = await get_user_trust_info(ride["driver_id"])
    
    safe_completion = await db.safe_completions.find_one({"ride_id": ride_id})
    
    accepted_requests = await db.ride_requests.find({
        "ride_id": ride_id,
        "status": "accepted"
    }).to_list(100)
    
    riders = []
    for req in accepted_requests:
        rider_trust = await get_user_trust_info(req["rider_id"])
        riders.append({
            "id": req["rider_id"],
            "name": req["rider_name"],
            "trust": rider_trust
        })
    
    # Get event tag info
    event_info = None
    if ride.get("event_tag"):
        all_tags = {t["id"]: t for t in EVENT_TAGS}
        custom_tags = await db.custom_events.find({}).to_list(100)
        for t in custom_tags:
            all_tags[t["id"]] = t
        tag_data = all_tags.get(ride["event_tag"])
        if tag_data:
            event_info = {
                "id": tag_data["id"],
                "name": tag_data["name"],
                "icon": tag_data["icon"],
                "color": tag_data["color"]
            }
    
    return {
        "id": ride["id"],
        "driverId": ride["driver_id"],
        "driverName": ride["driver_name"],
        "driverBranch": ride.get("driver_branch"),
        "driverYear": ride.get("driver_year"),
        "driverTrust": driver_trust,
        "source": ride["source"],
        "destination": ride["destination"],
        "departureTime": ride["departure_time"].isoformat(),
        "totalSeats": ride["total_seats"],
        "availableSeats": ride["available_seats"],
        "estimatedCost": ride["estimated_cost"],
        "costPerRider": round(cost_per_rider, 2),
        "pickupPoint": ride.get("pickup_point"),
        "isRecurring": ride.get("is_recurring", False),
        "recurrencePattern": ride.get("recurrence_pattern"),
        "eventTag": event_info,
        "distanceKm": ride.get("distance_km", AVERAGE_RIDE_DISTANCE_KM),
        "status": ride["status"],
        "safeCompletion": {
            "confirmed": safe_completion is not None,
            "confirmedAt": safe_completion["confirmed_at"].isoformat() if safe_completion else None,
            "confirmedBy": safe_completion["confirmed_by"] if safe_completion else None
        } if ride["status"] == "completed" else None,
        "riders": riders
    }

@app.get("/api/rides/driver/my-rides")
async def get_driver_rides(authorization: str = None):
    user = await get_current_user(authorization)
    
    if user["role"] != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can access this")
    
    cursor = db.rides.find({"driver_id": user["id"]}).sort("departure_time", -1)
    rides = await cursor.to_list(length=100)
    
    # Get event tags
    all_tags = {t["id"]: t for t in EVENT_TAGS}
    custom_tags = await db.custom_events.find({}).to_list(100)
    for t in custom_tags:
        all_tags[t["id"]] = t
    
    formatted_rides = []
    for ride in rides:
        occupied = ride["total_seats"] - ride["available_seats"]
        cost_per_rider = ride["estimated_cost"] / max(occupied, 1)
        
        pending_ratings = []
        if ride["status"] == "completed":
            accepted_requests = await db.ride_requests.find({
                "ride_id": ride["id"],
                "status": "accepted"
            }).to_list(100)
            
            for req in accepted_requests:
                existing_rating = await db.ratings.find_one({
                    "ride_id": ride["id"],
                    "rater_id": user["id"],
                    "rated_user_id": req["rider_id"]
                })
                if not existing_rating:
                    pending_ratings.append({
                        "userId": req["rider_id"],
                        "userName": req["rider_name"]
                    })
        
        event_info = None
        if ride.get("event_tag"):
            tag_data = all_tags.get(ride["event_tag"])
            if tag_data:
                event_info = {
                    "id": tag_data["id"],
                    "name": tag_data["name"],
                    "icon": tag_data["icon"],
                    "color": tag_data["color"]
                }
        
        formatted_rides.append({
            "id": ride["id"],
            "driverId": ride["driver_id"],
            "driverName": ride["driver_name"],
            "source": ride["source"],
            "destination": ride["destination"],
            "departureTime": ride["departure_time"].isoformat(),
            "totalSeats": ride["total_seats"],
            "availableSeats": ride["available_seats"],
            "estimatedCost": ride["estimated_cost"],
            "costPerRider": round(cost_per_rider, 2),
            "pickupPoint": ride.get("pickup_point"),
            "isRecurring": ride.get("is_recurring", False),
            "recurrencePattern": ride.get("recurrence_pattern"),
            "eventTag": event_info,
            "distanceKm": ride.get("distance_km", AVERAGE_RIDE_DISTANCE_KM),
            "status": ride["status"],
            "pendingRatings": pending_ratings
        })
    
    return {"rides": formatted_rides}

@app.patch("/api/rides/{ride_id}/status")
async def update_ride_status(ride_id: str, status: str, authorization: str = None):
    user = await get_current_user(authorization)
    
    ride = await db.rides.find_one({"id": ride_id})
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    if ride["driver_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if status not in ["posted", "in_progress", "completed", "cancelled"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    await db.rides.update_one(
        {"id": ride_id},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}}
    )
    
    return {"message": "Ride status updated successfully"}

# Ride Requests Routes
@app.post("/api/requests")
async def create_ride_request(request_data: RideRequestCreate, authorization: str = None):
    user = await get_current_user(authorization)
    
    if user["role"] != "rider":
        raise HTTPException(status_code=403, detail="Only riders can request rides")
    
    ride = await db.rides.find_one({"id": request_data.ride_id})
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    if ride["available_seats"] <= 0:
        raise HTTPException(status_code=400, detail="No available seats")
    
    if request_data.is_urgent:
        time_until_departure = (ride["departure_time"] - datetime.now(timezone.utc)).total_seconds() / 3600
        if time_until_departure > 2:
            raise HTTPException(
                status_code=400, 
                detail="Urgent requests are only allowed for rides departing within 2 hours"
            )
    
    existing = await db.ride_requests.find_one({
        "ride_id": request_data.ride_id,
        "rider_id": user["id"]
    })
    if existing:
        raise HTTPException(status_code=409, detail="You already requested this ride")
    
    request_id = str(uuid.uuid4())
    ride_request = {
        "id": request_id,
        "ride_id": request_data.ride_id,
        "rider_id": user["id"],
        "rider_name": user["name"],
        "rider_branch": user.get("branch"),
        "rider_year": user.get("academic_year"),
        "is_urgent": request_data.is_urgent,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    
    await db.ride_requests.insert_one(ride_request)
    
    return {
        "message": "Ride request sent successfully",
        "request": {
            "id": ride_request["id"],
            "rideId": ride_request["ride_id"],
            "riderId": ride_request["rider_id"],
            "riderName": ride_request["rider_name"],
            "isUrgent": ride_request["is_urgent"],
            "status": ride_request["status"]
        }
    }

@app.get("/api/requests/ride/{ride_id}")
async def get_ride_requests(ride_id: str, authorization: str = None):
    user = await get_current_user(authorization)
    
    ride = await db.rides.find_one({"id": ride_id})
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    if ride["driver_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    cursor = db.ride_requests.find({"ride_id": ride_id}).sort([
        ("is_urgent", -1),
        ("created_at", 1)
    ])
    requests = await cursor.to_list(length=100)
    
    result = []
    for req in requests:
        rider_trust = await get_user_trust_info(req["rider_id"])
        result.append({
            "id": req["id"],
            "rideId": req["ride_id"],
            "riderId": req["rider_id"],
            "riderName": req["rider_name"],
            "riderBranch": req.get("rider_branch"),
            "riderYear": req.get("rider_year"),
            "riderTrust": rider_trust,
            "isUrgent": req.get("is_urgent", False),
            "status": req["status"],
            "createdAt": req["created_at"].isoformat()
        })
    
    return {"requests": result}

@app.get("/api/requests/my-requests")
async def get_my_requests(authorization: str = None):
    user = await get_current_user(authorization)
    
    cursor = db.ride_requests.find({"rider_id": user["id"]}).sort("created_at", -1)
    requests = await cursor.to_list(length=100)
    
    result = []
    for req in requests:
        ride = await db.rides.find_one({"id": req["ride_id"]})
        if ride:
            pending_rating = None
            if req["status"] == "accepted" and ride["status"] == "completed":
                existing_rating = await db.ratings.find_one({
                    "ride_id": ride["id"],
                    "rater_id": user["id"],
                    "rated_user_id": ride["driver_id"]
                })
                if not existing_rating:
                    pending_rating = {
                        "userId": ride["driver_id"],
                        "userName": ride["driver_name"]
                    }
            
            safe_completion = await db.safe_completions.find_one({
                "ride_id": ride["id"],
                "confirmed_by": user["id"]
            })
            
            result.append({
                "id": req["id"],
                "rideId": req["ride_id"],
                "isUrgent": req.get("is_urgent", False),
                "status": req["status"],
                "createdAt": req["created_at"].isoformat(),
                "ride": {
                    "source": ride["source"],
                    "destination": ride["destination"],
                    "departureTime": ride["departure_time"].isoformat(),
                    "driverName": ride["driver_name"],
                    "driverId": ride["driver_id"],
                    "pickupPoint": ride.get("pickup_point"),
                    "status": ride["status"],
                    "estimatedCost": ride["estimated_cost"]
                },
                "pendingRating": pending_rating,
                "safelyConfirmed": safe_completion is not None
            })
    
    return {"requests": result}

@app.patch("/api/requests/{request_id}/accept")
async def accept_request(request_id: str, authorization: str = None):
    user = await get_current_user(authorization)
    
    request = await db.ride_requests.find_one({"id": request_id})
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    ride = await db.rides.find_one({"id": request["ride_id"]})
    if ride["driver_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if ride["available_seats"] <= 0:
        raise HTTPException(status_code=400, detail="No available seats")
    
    await db.ride_requests.update_one(
        {"id": request_id},
        {"$set": {"status": "accepted", "updated_at": datetime.now(timezone.utc)}}
    )
    
    await db.rides.update_one(
        {"id": request["ride_id"]},
        {"$inc": {"available_seats": -1}, "$set": {"updated_at": datetime.now(timezone.utc)}}
    )
    
    return {"message": "Request accepted successfully"}

@app.patch("/api/requests/{request_id}/reject")
async def reject_request(request_id: str, authorization: str = None):
    user = await get_current_user(authorization)
    
    request = await db.ride_requests.find_one({"id": request_id})
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    ride = await db.rides.find_one({"id": request["ride_id"]})
    if ride["driver_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    await db.ride_requests.update_one(
        {"id": request_id},
        {"$set": {"status": "rejected", "updated_at": datetime.now(timezone.utc)}}
    )
    
    return {"message": "Request rejected successfully"}

# Rating Routes
@app.post("/api/ratings")
async def create_rating(rating_data: RatingCreate, authorization: str = None):
    user = await get_current_user(authorization)
    
    ride = await db.rides.find_one({"id": rating_data.ride_id})
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    if ride["status"] != "completed":
        raise HTTPException(status_code=400, detail="Can only rate completed rides")
    
    is_driver = ride["driver_id"] == user["id"]
    is_rider = await db.ride_requests.find_one({
        "ride_id": rating_data.ride_id,
        "rider_id": user["id"],
        "status": "accepted"
    })
    
    if not is_driver and not is_rider:
        raise HTTPException(status_code=403, detail="You were not part of this ride")
    
    rated_is_driver = ride["driver_id"] == rating_data.rated_user_id
    rated_is_rider = await db.ride_requests.find_one({
        "ride_id": rating_data.ride_id,
        "rider_id": rating_data.rated_user_id,
        "status": "accepted"
    })
    
    if not rated_is_driver and not rated_is_rider:
        raise HTTPException(status_code=400, detail="Rated user was not part of this ride")
    
    if user["id"] == rating_data.rated_user_id:
        raise HTTPException(status_code=400, detail="Cannot rate yourself")
    
    existing = await db.ratings.find_one({
        "ride_id": rating_data.ride_id,
        "rater_id": user["id"],
        "rated_user_id": rating_data.rated_user_id
    })
    if existing:
        raise HTTPException(status_code=409, detail="You already rated this user for this ride")
    
    rating_id = str(uuid.uuid4())
    rating = {
        "id": rating_id,
        "ride_id": rating_data.ride_id,
        "rater_id": user["id"],
        "rater_name": user["name"],
        "rated_user_id": rating_data.rated_user_id,
        "rating": rating_data.rating,
        "feedback": rating_data.feedback,
        "created_at": datetime.now(timezone.utc)
    }
    
    await db.ratings.insert_one(rating)
    
    return {"message": "Rating submitted successfully", "rating_id": rating_id}

@app.get("/api/ratings/user/{user_id}")
async def get_user_ratings(user_id: str):
    """Get aggregated rating info for a user"""
    pipeline = [
        {"$match": {"rated_user_id": user_id}},
        {"$group": {
            "_id": None,
            "avgRating": {"$avg": "$rating"},
            "count": {"$sum": 1},
            "stars": {"$push": "$rating"}
        }}
    ]
    result = await db.ratings.aggregate(pipeline).to_list(1)
    
    if not result:
        return {
            "avgRating": 0,
            "totalRatings": 0,
            "distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        }
    
    distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for star in result[0]["stars"]:
        distribution[star] = distribution.get(star, 0) + 1
    
    return {
        "avgRating": round(result[0]["avgRating"], 1),
        "totalRatings": result[0]["count"],
        "distribution": distribution
    }

# Safe Completion Routes
@app.post("/api/safe-completion")
async def confirm_safe_completion(data: SafeCompletionCreate, authorization: str = None):
    user = await get_current_user(authorization)
    
    ride = await db.rides.find_one({"id": data.ride_id})
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    ride_request = await db.ride_requests.find_one({
        "ride_id": data.ride_id,
        "rider_id": user["id"],
        "status": "accepted"
    })
    if not ride_request:
        raise HTTPException(status_code=403, detail="Only accepted riders can confirm safe completion")
    
    existing = await db.safe_completions.find_one({
        "ride_id": data.ride_id,
        "confirmed_by": user["id"]
    })
    if existing:
        raise HTTPException(status_code=409, detail="You already confirmed safe completion")
    
    completion_id = str(uuid.uuid4())
    safe_completion = {
        "id": completion_id,
        "ride_id": data.ride_id,
        "confirmed_by": user["id"],
        "confirmed_by_name": user["name"],
        "confirmed_at": datetime.now(timezone.utc)
    }
    
    await db.safe_completions.insert_one(safe_completion)
    
    return {"message": "Safe completion confirmed", "completion_id": completion_id}

@app.get("/api/safe-completion/ride/{ride_id}")
async def get_ride_safe_completions(ride_id: str, authorization: str = None):
    await get_current_user(authorization)
    
    cursor = db.safe_completions.find({"ride_id": ride_id})
    completions = await cursor.to_list(100)
    
    return {
        "completions": [{
            "id": c["id"],
            "confirmedBy": c["confirmed_by"],
            "confirmedByName": c["confirmed_by_name"],
            "confirmedAt": c["confirmed_at"].isoformat()
        } for c in completions]
    }

# Ride History Routes
@app.get("/api/history/driver")
async def get_driver_history(authorization: str = None):
    user = await get_current_user(authorization)
    
    if user["role"] != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can access this")
    
    cursor = db.rides.find({
        "driver_id": user["id"],
        "status": {"$in": ["completed", "cancelled"]}
    }).sort("departure_time", -1)
    rides = await cursor.to_list(length=100)
    
    history = []
    for ride in rides:
        accepted_requests = await db.ride_requests.find({
            "ride_id": ride["id"],
            "status": "accepted"
        }).to_list(100)
        
        riders_count = len(accepted_requests)
        actual_cost = ride["estimated_cost"] / max(riders_count, 1) if riders_count > 0 else ride["estimated_cost"]
        
        safe_completions = await db.safe_completions.count_documents({"ride_id": ride["id"]})
        
        history.append({
            "id": ride["id"],
            "source": ride["source"],
            "destination": ride["destination"],
            "departureTime": ride["departure_time"].isoformat(),
            "status": ride["status"],
            "totalSeats": ride["total_seats"],
            "ridersCount": riders_count,
            "estimatedCost": ride["estimated_cost"],
            "actualCostPerRider": round(actual_cost, 2),
            "safeCompletions": safe_completions,
            "distanceKm": ride.get("distance_km", AVERAGE_RIDE_DISTANCE_KM),
            "role": "driver"
        })
    
    return {"history": history}

@app.get("/api/history/rider")
async def get_rider_history(authorization: str = None):
    user = await get_current_user(authorization)
    
    cursor = db.ride_requests.find({
        "rider_id": user["id"],
        "status": "accepted"
    }).sort("created_at", -1)
    requests = await cursor.to_list(length=100)
    
    history = []
    for req in requests:
        ride = await db.rides.find_one({"id": req["ride_id"]})
        if ride and ride["status"] in ["completed", "cancelled"]:
            accepted_count = await db.ride_requests.count_documents({
                "ride_id": ride["id"],
                "status": "accepted"
            })
            cost_per_rider = ride["estimated_cost"] / max(accepted_count, 1)
            
            safe_completion = await db.safe_completions.find_one({
                "ride_id": ride["id"],
                "confirmed_by": user["id"]
            })
            
            history.append({
                "id": ride["id"],
                "source": ride["source"],
                "destination": ride["destination"],
                "departureTime": ride["departure_time"].isoformat(),
                "status": ride["status"],
                "driverName": ride["driver_name"],
                "driverId": ride["driver_id"],
                "costPaid": round(cost_per_rider, 2),
                "safelyConfirmed": safe_completion is not None,
                "distanceKm": ride.get("distance_km", AVERAGE_RIDE_DISTANCE_KM),
                "role": "rider"
            })
    
    return {"history": history}

# =============================================================================
# ADMIN ROUTES - Phase 8: Admin, Moderation & Governance
# =============================================================================

# --- SOS Events Routes ---
@app.post("/api/sos")
async def create_sos_event(sos_data: SOSEventCreate, user: dict = Depends(get_current_user)):
    """Create an SOS/Emergency event for a ride"""
    ride = await db.rides.find_one({"id": sos_data.ride_id})
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    # Check user is part of the ride
    is_driver = ride["driver_id"] == user["id"]
    is_rider = await db.ride_requests.find_one({
        "ride_id": sos_data.ride_id,
        "rider_id": user["id"],
        "status": "accepted"
    })
    
    if not is_driver and not is_rider:
        raise HTTPException(status_code=403, detail="You are not part of this ride")
    
    sos_id = str(uuid.uuid4())
    sos_event = {
        "id": sos_id,
        "ride_id": sos_data.ride_id,
        "reporter_id": user["id"],
        "reporter_name": user["name"],
        "description": sos_data.description,
        "location": sos_data.location,
        "status": "active",
        "admin_notes": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    
    await db.sos_events.insert_one(sos_event)
    
    return {"message": "SOS event created", "sos_id": sos_id}

@app.get("/api/sos/my-events")
async def get_my_sos_events(user: dict = Depends(get_current_user)):
    """Get SOS events created by the current user"""
    cursor = db.sos_events.find({"reporter_id": user["id"]}).sort("created_at", -1)
    events = await cursor.to_list(100)
    
    result = []
    for event in events:
        ride = await db.rides.find_one({"id": event["ride_id"]})
        result.append({
            "id": event["id"],
            "rideId": event["ride_id"],
            "description": event["description"],
            "location": event.get("location"),
            "status": event["status"],
            "createdAt": event["created_at"].isoformat(),
            "ride": {
                "source": ride["source"] if ride else "N/A",
                "destination": ride["destination"] if ride else "N/A"
            } if ride else None
        })
    
    return {"events": result}

# --- Report Routes ---
@app.post("/api/reports")
async def create_report(report_data: ReportCreate, user: dict = Depends(get_current_user)):
    """Submit a report against a user or ride"""
    # Validate target exists
    if report_data.target_type == "user":
        target = await db.users.find_one({"id": report_data.target_id})
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
    else:
        target = await db.rides.find_one({"id": report_data.target_id})
        if not target:
            raise HTTPException(status_code=404, detail="Ride not found")
    
    report_id = str(uuid.uuid4())
    report = {
        "id": report_id,
        "reporter_id": user["id"],
        "reporter_name": user["name"],
        "target_type": report_data.target_type,
        "target_id": report_data.target_id,
        "category": report_data.category,
        "description": report_data.description,
        "status": "pending",
        "action_taken": None,
        "admin_note": None,
        "reviewed_by": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    
    await db.reports.insert_one(report)
    
    return {"message": "Report submitted successfully", "report_id": report_id}

@app.get("/api/reports/my-reports")
async def get_my_reports(user: dict = Depends(get_current_user)):
    """Get reports submitted by the current user"""
    cursor = db.reports.find({"reporter_id": user["id"]}).sort("created_at", -1)
    reports = await cursor.to_list(100)
    
    result = []
    for report in reports:
        result.append({
            "id": report["id"],
            "targetType": report["target_type"],
            "targetId": report["target_id"],
            "category": report["category"],
            "description": report["description"],
            "status": report["status"],
            "createdAt": report["created_at"].isoformat()
        })
    
    return {"reports": result}

# --- Admin User Management Routes ---
@app.get("/api/admin/users")
async def admin_get_users(
    admin: dict = Depends(get_admin_user),
    role: Optional[str] = None,
    is_verified: Optional[bool] = None,
    is_disabled: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """Get all users with optional filters (Admin only)"""
    query = {}
    
    if role:
        query["role"] = role
    if is_verified is not None:
        query["is_verified"] = is_verified
    if is_disabled is not None:
        query["is_disabled"] = is_disabled
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}}
        ]
    
    total = await db.users.count_documents(query)
    cursor = db.users.find(query).sort("created_at", -1).skip(offset).limit(limit)
    users = await cursor.to_list(length=limit)
    
    result = []
    for user in users:
        trust_info = await get_user_trust_info(user["id"])
        stats = await calculate_user_statistics(user["id"])
        result.append({
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "branch": user.get("branch"),
            "academicYear": user.get("academic_year"),
            "isVerified": user.get("is_verified", False),
            "isDisabled": user.get("is_disabled", False),
            "isSuspended": user.get("is_suspended", False),
            "warningsCount": len(user.get("warnings", [])),
            "createdAt": user["created_at"].isoformat() if user.get("created_at") else None,
            "trustInfo": trust_info,
            "statistics": stats
        })
    
    return {
        "users": result,
        "total": total,
        "limit": limit,
        "offset": offset
    }

@app.get("/api/admin/users/{user_id}")
async def admin_get_user_details(user_id: str, admin: dict = Depends(get_admin_user)):
    """Get detailed user information (Admin only)"""
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    trust_info = await get_user_trust_info(user_id)
    stats = await calculate_user_statistics(user_id)
    badges = await get_user_badges(user_id)
    
    # Get verification history
    verifications = await db.user_verifications.find({"user_id": user_id}).sort("created_at", -1).to_list(50)
    
    # Get reports against this user
    reports_against = await db.reports.find({
        "target_type": "user",
        "target_id": user_id
    }).sort("created_at", -1).to_list(50)
    
    # Get SOS events involving this user
    sos_events = await db.sos_events.find({"reporter_id": user_id}).sort("created_at", -1).to_list(50)
    
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "branch": user.get("branch"),
        "academicYear": user.get("academic_year"),
        "isVerified": user.get("is_verified", False),
        "isDisabled": user.get("is_disabled", False),
        "isSuspended": user.get("is_suspended", False),
        "warnings": user.get("warnings", []),
        "createdAt": user["created_at"].isoformat() if user.get("created_at") else None,
        "updatedAt": user["updated_at"].isoformat() if user.get("updated_at") else None,
        "trustInfo": trust_info,
        "statistics": stats,
        "badges": badges,
        "verificationHistory": [{
            "id": v["id"],
            "action": v["action"],
            "adminName": v["admin_name"],
            "reason": v.get("reason"),
            "createdAt": v["created_at"].isoformat()
        } for v in verifications],
        "reportsAgainst": [{
            "id": r["id"],
            "category": r["category"],
            "description": r["description"],
            "status": r["status"],
            "createdAt": r["created_at"].isoformat()
        } for r in reports_against],
        "sosEvents": [{
            "id": e["id"],
            "rideId": e["ride_id"],
            "status": e["status"],
            "createdAt": e["created_at"].isoformat()
        } for e in sos_events]
    }

@app.post("/api/admin/users/{user_id}/action")
async def admin_user_action(user_id: str, action_data: UserActionRequest, admin: dict = Depends(get_admin_user)):
    """Take action on a user (warn, suspend, disable, enable) - Admin only"""
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    update_fields = {"updated_at": datetime.now(timezone.utc)}
    action_details = action_data.reason or "No reason provided"
    
    if action_data.action == "warn":
        warning = {
            "id": str(uuid.uuid4()),
            "admin_id": admin["id"],
            "admin_name": admin["name"],
            "reason": action_data.reason,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.users.update_one(
            {"id": user_id},
            {"$push": {"warnings": warning}, "$set": update_fields}
        )
    elif action_data.action == "suspend":
        update_fields["is_suspended"] = True
        await db.users.update_one({"id": user_id}, {"$set": update_fields})
    elif action_data.action == "disable":
        update_fields["is_disabled"] = True
        await db.users.update_one({"id": user_id}, {"$set": update_fields})
    elif action_data.action == "enable":
        update_fields["is_disabled"] = False
        update_fields["is_suspended"] = False
        await db.users.update_one({"id": user_id}, {"$set": update_fields})
    
    # Log the admin action
    await log_admin_action(
        admin["id"], admin["name"], action_data.action, "user", user_id, action_details
    )
    
    return {"message": f"User {action_data.action} action completed successfully"}

@app.post("/api/admin/users/{user_id}/verification")
async def admin_user_verification(user_id: str, verify_data: VerificationRequest, admin: dict = Depends(get_admin_user)):
    """Verify or revoke verification for a user - Admin only"""
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    is_verified = verify_data.action == "verify"
    
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"is_verified": is_verified, "updated_at": datetime.now(timezone.utc)}}
    )
    
    # Create verification history record
    verification_record = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "action": verify_data.action,
        "admin_id": admin["id"],
        "admin_name": admin["name"],
        "reason": verify_data.reason,
        "created_at": datetime.now(timezone.utc)
    }
    await db.user_verifications.insert_one(verification_record)
    
    # Log the admin action
    await log_admin_action(
        admin["id"], admin["name"], verify_data.action, "user", user_id,
        verify_data.reason or f"Verification {verify_data.action}"
    )
    
    return {"message": f"User verification {verify_data.action} completed"}

# --- Admin Ride Monitoring Routes ---
@app.get("/api/admin/rides")
async def admin_get_rides(
    admin: dict = Depends(get_admin_user),
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    driver_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """Get all rides with filters (Admin only)"""
    query = {}
    
    if status:
        query["status"] = status
    if driver_id:
        query["driver_id"] = driver_id
    if date_from:
        try:
            start = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            query.setdefault("departure_time", {})["$gte"] = start
        except:
            pass
    if date_to:
        try:
            end = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            query.setdefault("departure_time", {})["$lte"] = end
        except:
            pass
    
    total = await db.rides.count_documents(query)
    cursor = db.rides.find(query).sort("departure_time", -1).skip(offset).limit(limit)
    rides = await cursor.to_list(length=limit)
    
    result = []
    for ride in rides:
        # Get participants count
        participants_count = await db.ride_requests.count_documents({
            "ride_id": ride["id"],
            "status": "accepted"
        })
        
        result.append({
            "id": ride["id"],
            "driverId": ride["driver_id"],
            "driverName": ride["driver_name"],
            "source": ride["source"],
            "destination": ride["destination"],
            "departureTime": ride["departure_time"].isoformat(),
            "status": ride["status"],
            "totalSeats": ride["total_seats"],
            "availableSeats": ride["available_seats"],
            "participantsCount": participants_count,
            "estimatedCost": ride["estimated_cost"],
            "createdAt": ride["created_at"].isoformat() if ride.get("created_at") else None
        })
    
    return {
        "rides": result,
        "total": total,
        "limit": limit,
        "offset": offset
    }

@app.get("/api/admin/rides/abnormal")
async def admin_get_abnormal_rides(admin: dict = Depends(get_admin_user)):
    """Get rides with abnormal patterns (frequently cancelled drivers) - Admin only"""
    # Find drivers with high cancellation rates
    pipeline = [
        {"$group": {
            "_id": "$driver_id",
            "total": {"$sum": 1},
            "cancelled": {"$sum": {"$cond": [{"$eq": ["$status", "cancelled"]}, 1, 0]}}
        }},
        {"$match": {
            "total": {"$gte": 3},
            "$expr": {"$gte": [{"$divide": ["$cancelled", "$total"]}, 0.5]}
        }},
        {"$sort": {"cancelled": -1}},
        {"$limit": 50}
    ]
    
    results = await db.rides.aggregate(pipeline).to_list(50)
    
    abnormal_drivers = []
    for r in results:
        user = await db.users.find_one({"id": r["_id"]})
        if user:
            abnormal_drivers.append({
                "driverId": r["_id"],
                "driverName": user["name"],
                "totalRides": r["total"],
                "cancelledRides": r["cancelled"],
                "cancellationRate": round(r["cancelled"] / r["total"] * 100, 1)
            })
    
    return {"abnormalDrivers": abnormal_drivers}

@app.get("/api/admin/rides/{ride_id}")
async def admin_get_ride_details(ride_id: str, admin: dict = Depends(get_admin_user)):
    """Get detailed ride information (Admin only)"""
    ride = await db.rides.find_one({"id": ride_id})
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    # Get driver info
    driver = await db.users.find_one({"id": ride["driver_id"]})
    driver_trust = await get_user_trust_info(ride["driver_id"])
    
    # Get all requests for this ride
    requests = await db.ride_requests.find({"ride_id": ride_id}).to_list(100)
    
    # Get safe completions
    safe_completions = await db.safe_completions.find({"ride_id": ride_id}).to_list(100)
    
    # Get SOS events
    sos_events = await db.sos_events.find({"ride_id": ride_id}).to_list(100)
    
    # Get reports for this ride
    reports = await db.reports.find({
        "target_type": "ride",
        "target_id": ride_id
    }).to_list(100)
    
    return {
        "id": ride["id"],
        "driver": {
            "id": driver["id"],
            "name": driver["name"],
            "email": driver["email"],
            "trustInfo": driver_trust
        } if driver else None,
        "source": ride["source"],
        "destination": ride["destination"],
        "departureTime": ride["departure_time"].isoformat(),
        "status": ride["status"],
        "totalSeats": ride["total_seats"],
        "availableSeats": ride["available_seats"],
        "estimatedCost": ride["estimated_cost"],
        "pickupPoint": ride.get("pickup_point"),
        "distanceKm": ride.get("distance_km"),
        "createdAt": ride["created_at"].isoformat() if ride.get("created_at") else None,
        "requests": [{
            "id": r["id"],
            "riderId": r["rider_id"],
            "riderName": r["rider_name"],
            "status": r["status"],
            "isUrgent": r.get("is_urgent", False),
            "createdAt": r["created_at"].isoformat()
        } for r in requests],
        "safeCompletions": [{
            "id": s["id"],
            "confirmedBy": s["confirmed_by"],
            "confirmedByName": s["confirmed_by_name"],
            "confirmedAt": s["confirmed_at"].isoformat()
        } for s in safe_completions],
        "sosEvents": [{
            "id": e["id"],
            "reporterName": e["reporter_name"],
            "description": e["description"],
            "status": e["status"],
            "createdAt": e["created_at"].isoformat()
        } for e in sos_events],
        "reports": [{
            "id": r["id"],
            "category": r["category"],
            "description": r["description"],
            "status": r["status"],
            "createdAt": r["created_at"].isoformat()
        } for r in reports]
    }

# --- Admin SOS Management Routes ---
@app.get("/api/admin/sos")
async def admin_get_sos_events(
    admin: dict = Depends(get_admin_user),
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """Get all SOS events (Admin only)"""
    query = {}
    if status:
        query["status"] = status
    
    total = await db.sos_events.count_documents(query)
    cursor = db.sos_events.find(query).sort("created_at", -1).skip(offset).limit(limit)
    events = await cursor.to_list(length=limit)
    
    result = []
    for event in events:
        ride = await db.rides.find_one({"id": event["ride_id"]})
        result.append({
            "id": event["id"],
            "rideId": event["ride_id"],
            "reporterId": event["reporter_id"],
            "reporterName": event["reporter_name"],
            "description": event["description"],
            "location": event.get("location"),
            "status": event["status"],
            "adminNotes": event.get("admin_notes", []),
            "createdAt": event["created_at"].isoformat(),
            "ride": {
                "source": ride["source"],
                "destination": ride["destination"],
                "driverName": ride["driver_name"],
                "status": ride["status"]
            } if ride else None
        })
    
    return {
        "events": result,
        "total": total,
        "limit": limit,
        "offset": offset
    }

@app.patch("/api/admin/sos/{sos_id}")
async def admin_update_sos(sos_id: str, update_data: SOSStatusUpdate, admin: dict = Depends(get_admin_user)):
    """Update SOS event status and add notes (Admin only)"""
    event = await db.sos_events.find_one({"id": sos_id})
    if not event:
        raise HTTPException(status_code=404, detail="SOS event not found")
    
    update_fields = {
        "status": update_data.status,
        "updated_at": datetime.now(timezone.utc)
    }
    
    # Add admin note if provided
    if update_data.admin_note:
        admin_note = {
            "admin_id": admin["id"],
            "admin_name": admin["name"],
            "note": update_data.admin_note,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.sos_events.update_one(
            {"id": sos_id},
            {"$push": {"admin_notes": admin_note}, "$set": update_fields}
        )
    else:
        await db.sos_events.update_one({"id": sos_id}, {"$set": update_fields})
    
    # Log admin action
    await log_admin_action(
        admin["id"], admin["name"], f"sos_status_update_{update_data.status}",
        "sos_event", sos_id, update_data.admin_note
    )
    
    return {"message": "SOS event updated successfully"}

# --- Admin Report Management Routes ---
@app.get("/api/admin/reports")
async def admin_get_reports(
    admin: dict = Depends(get_admin_user),
    status: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """Get all reports (Admin only)"""
    query = {}
    if status:
        query["status"] = status
    if category:
        query["category"] = category
    
    total = await db.reports.count_documents(query)
    cursor = db.reports.find(query).sort("created_at", -1).skip(offset).limit(limit)
    reports = await cursor.to_list(length=limit)
    
    result = []
    for report in reports:
        # Get target info
        target_info = None
        if report["target_type"] == "user":
            target = await db.users.find_one({"id": report["target_id"]})
            if target:
                target_info = {"name": target["name"], "email": target["email"]}
        else:
            target = await db.rides.find_one({"id": report["target_id"]})
            if target:
                target_info = {
                    "source": target["source"],
                    "destination": target["destination"],
                    "driverName": target["driver_name"]
                }
        
        result.append({
            "id": report["id"],
            "reporterId": report["reporter_id"],
            "reporterName": report["reporter_name"],
            "targetType": report["target_type"],
            "targetId": report["target_id"],
            "targetInfo": target_info,
            "category": report["category"],
            "description": report["description"],
            "status": report["status"],
            "actionTaken": report.get("action_taken"),
            "adminNote": report.get("admin_note"),
            "reviewedBy": report.get("reviewed_by"),
            "createdAt": report["created_at"].isoformat()
        })
    
    return {
        "reports": result,
        "total": total,
        "limit": limit,
        "offset": offset
    }

@app.patch("/api/admin/reports/{report_id}")
async def admin_update_report(report_id: str, update_data: ReportStatusUpdate, admin: dict = Depends(get_admin_user)):
    """Update report status (Admin only)"""
    report = await db.reports.find_one({"id": report_id})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    update_fields = {
        "status": update_data.status,
        "reviewed_by": admin["id"],
        "updated_at": datetime.now(timezone.utc)
    }
    
    if update_data.action_taken:
        update_fields["action_taken"] = update_data.action_taken
    if update_data.admin_note:
        update_fields["admin_note"] = update_data.admin_note
    
    await db.reports.update_one({"id": report_id}, {"$set": update_fields})
    
    # Log admin action
    await log_admin_action(
        admin["id"], admin["name"], f"report_status_update_{update_data.status}",
        "report", report_id, f"Action: {update_data.action_taken or 'None'}"
    )
    
    return {"message": "Report updated successfully"}

# --- Admin Analytics Routes ---
@app.get("/api/admin/analytics")
async def admin_get_analytics(admin: dict = Depends(get_admin_user)):
    """Get platform analytics overview (Admin only)"""
    # User stats
    total_users = await db.users.count_documents({})
    verified_users = await db.users.count_documents({"is_verified": True})
    disabled_users = await db.users.count_documents({"is_disabled": True})
    drivers = await db.users.count_documents({"role": "driver"})
    riders = await db.users.count_documents({"role": "rider"})
    
    # Ride stats
    total_rides = await db.rides.count_documents({})
    active_rides = await db.rides.count_documents({"status": "posted"})
    completed_rides = await db.rides.count_documents({"status": "completed"})
    cancelled_rides = await db.rides.count_documents({"status": "cancelled"})
    
    # SOS stats
    total_sos = await db.sos_events.count_documents({})
    active_sos = await db.sos_events.count_documents({"status": "active"})
    
    # Report stats
    total_reports = await db.reports.count_documents({})
    pending_reports = await db.reports.count_documents({"status": "pending"})
    
    # Rating stats
    total_ratings = await db.ratings.count_documents({})
    
    # Safe completions
    total_safe_completions = await db.safe_completions.count_documents({})
    
    # Calculate global eco impact
    all_completed = await db.rides.find({"status": "completed"}).to_list(10000)
    total_distance = sum(r.get("distance_km", AVERAGE_RIDE_DISTANCE_KM) for r in all_completed)
    total_co2_saved = total_distance * CO2_PER_KM_SOLO * CO2_SAVINGS_FACTOR
    
    # Active users (last 7 days)
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    active_drivers_7d = await db.rides.distinct("driver_id", {
        "created_at": {"$gte": seven_days_ago}
    })
    active_riders_7d = await db.ride_requests.distinct("rider_id", {
        "created_at": {"$gte": seven_days_ago}
    })
    active_users_7d = len(set(active_drivers_7d + active_riders_7d))
    
    # Active users (last 30 days)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    active_drivers_30d = await db.rides.distinct("driver_id", {
        "created_at": {"$gte": thirty_days_ago}
    })
    active_riders_30d = await db.ride_requests.distinct("rider_id", {
        "created_at": {"$gte": thirty_days_ago}
    })
    active_users_30d = len(set(active_drivers_30d + active_riders_30d))
    
    return {
        "users": {
            "total": total_users,
            "verified": verified_users,
            "disabled": disabled_users,
            "drivers": drivers,
            "riders": riders,
            "activeUsers7d": active_users_7d,
            "activeUsers30d": active_users_30d
        },
        "rides": {
            "total": total_rides,
            "active": active_rides,
            "completed": completed_rides,
            "cancelled": cancelled_rides
        },
        "safety": {
            "totalSOS": total_sos,
            "activeSOS": active_sos,
            "totalReports": total_reports,
            "pendingReports": pending_reports,
            "safeCompletions": total_safe_completions
        },
        "engagement": {
            "totalRatings": total_ratings,
            "completionRate": round(completed_rides / max(total_rides, 1) * 100, 1)
        },
        "ecoImpact": {
            "totalDistanceKm": round(total_distance, 1),
            "totalCo2SavedKg": round(total_co2_saved, 2),
            "treesEquivalent": round(total_co2_saved / 21, 1)
        }
    }

# --- Admin Audit Logs Routes ---
@app.get("/api/admin/audit-logs")
async def admin_get_audit_logs(
    admin: dict = Depends(get_admin_user),
    admin_id: Optional[str] = None,
    action_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """Get admin audit logs (Admin only)"""
    query = {}
    if admin_id:
        query["admin_id"] = admin_id
    if action_type:
        query["action_type"] = action_type
    
    total = await db.admin_audit_logs.count_documents(query)
    cursor = db.admin_audit_logs.find(query).sort("created_at", -1).skip(offset).limit(limit)
    logs = await cursor.to_list(length=limit)
    
    result = []
    for log in logs:
        result.append({
            "id": log["id"],
            "adminId": log["admin_id"],
            "adminName": log["admin_name"],
            "actionType": log["action_type"],
            "targetType": log["target_type"],
            "targetId": log["target_id"],
            "details": log.get("details"),
            "createdAt": log["created_at"].isoformat()
        })
    
    return {
        "logs": result,
        "total": total,
        "limit": limit,
        "offset": offset
    }

# --- Stats Routes (Public) ---
@app.get("/api/stats")
async def get_stats(authorization: str = None):
    user = await get_current_user(authorization)
    
    total_users = await db.users.count_documents({})
    total_rides = await db.rides.count_documents({})
    total_requests = await db.ride_requests.count_documents({})
    active_rides = await db.rides.count_documents({"status": "posted"})
    completed_rides = await db.rides.count_documents({"status": "completed"})
    urgent_requests = await db.ride_requests.count_documents({"is_urgent": True, "status": "pending"})
    total_ratings = await db.ratings.count_documents({})
    safe_completions = await db.safe_completions.count_documents({})
    
    # Calculate global eco impact
    all_completed = await db.rides.find({"status": "completed"}).to_list(10000)
    total_distance = sum(r.get("distance_km", AVERAGE_RIDE_DISTANCE_KM) for r in all_completed)
    total_co2_saved = total_distance * CO2_PER_KM_SOLO * CO2_SAVINGS_FACTOR
    
    return {
        "totalUsers": total_users,
        "totalRides": total_rides,
        "totalRequests": total_requests,
        "activeRides": active_rides,
        "completedRides": completed_rides,
        "urgentPendingRequests": urgent_requests,
        "totalRatings": total_ratings,
        "safeCompletions": safe_completions,
        "globalEcoImpact": {
            "totalDistanceKm": round(total_distance, 1),
            "totalCo2SavedKg": round(total_co2_saved, 2)
        }
    }

# Badge Definitions Route
@app.get("/api/badges")
async def get_all_badges():
    """Get all available badge definitions"""
    return {"badges": BADGE_DEFINITIONS}

# Report Categories Route
@app.get("/api/report-categories")
async def get_report_categories():
    """Get all available report categories"""
    return {"categories": REPORT_CATEGORIES}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
