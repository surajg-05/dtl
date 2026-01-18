from fastapi import FastAPI, HTTPException, Depends, status, Header
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
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

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

# Admin/Stats Routes
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
