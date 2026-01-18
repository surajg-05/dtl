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
    await db.rides.create_index([("source", "text"), ("destination", "text")])
    await db.ride_requests.create_index("ride_id")
    await db.ride_requests.create_index("is_urgent")
    await db.ratings.create_index([("ride_id", 1), ("rater_id", 1)], unique=True)
    await db.ratings.create_index("rated_user_id")
    await db.safe_completions.create_index("ride_id")
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
    role: str = Field(..., pattern="^(rider|driver)$")

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class RideCreate(BaseModel):
    source: str = Field(..., min_length=2)
    destination: str = Field(..., min_length=2)
    departure_time: datetime
    total_seats: int = Field(..., ge=1, le=8)
    estimated_cost: float = Field(..., ge=0)
    pickup_point: Optional[str] = None
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None  # 'weekdays', 'daily', 'weekly'

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
    
    # Source matching
    if search_source:
        ride_source_lower = ride_source.lower()
        search_source_lower = search_source.lower()
        if search_source_lower in ride_source_lower or ride_source_lower in search_source_lower:
            score += 50
        elif any(word in ride_source_lower for word in search_source_lower.split()):
            score += 25
    
    # Destination matching
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
        # Generate for next 2 weeks of weekdays
        for i in range(1, 15):
            next_date = base_time + timedelta(days=i)
            if next_date.weekday() < 5:  # Monday = 0, Friday = 4
                new_ride = ride_data.copy()
                new_ride["id"] = str(uuid.uuid4())
                new_ride["departure_time"] = next_date
                new_ride["parent_ride_id"] = ride_data["id"]
                rides_to_create.append(new_ride)
    elif pattern == "daily":
        # Generate for next 7 days
        for i in range(1, 8):
            new_ride = ride_data.copy()
            new_ride["id"] = str(uuid.uuid4())
            new_ride["departure_time"] = base_time + timedelta(days=i)
            new_ride["parent_ride_id"] = ride_data["id"]
            rides_to_create.append(new_ride)
    elif pattern == "weekly":
        # Generate for next 4 weeks
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
    # Get completed rides count (as driver or rider)
    driver_rides = await db.rides.count_documents({"driver_id": user_id, "status": "completed"})
    rider_requests = await db.ride_requests.count_documents({"rider_id": user_id, "status": "accepted"})
    total_rides = driver_rides + rider_requests
    
    # Get average rating
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
    
    # Determine trust label
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

# API Routes

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "CampusPool API"}

@app.get("/api/pickup-points")
async def get_pickup_points():
    return {"pickup_points": PICKUP_POINTS}

# Auth Routes
@app.post("/api/auth/signup", response_model=TokenResponse)
async def signup(user_data: UserSignup):
    # Check if email exists
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
            "role": user["role"]
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
            "role": user["role"]
        }
    }

@app.get("/api/auth/me")
async def get_current_user_info(user: dict = Depends(get_current_user)):
    trust_info = await get_user_trust_info(user["id"])
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        **trust_info
    }

# User Profile Routes
@app.get("/api/users/{user_id}/profile")
async def get_user_profile(user_id: str):
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    trust_info = await get_user_trust_info(user_id)
    
    return {
        "id": user["id"],
        "name": user["name"],
        "role": user["role"],
        "createdAt": user["created_at"].isoformat() if user.get("created_at") else None,
        **trust_info
    }

# Rides Routes
@app.post("/api/rides")
async def create_ride(ride_data: RideCreate, user: dict = Depends(get_current_user)):
    
    if user["role"] != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can post rides")
    
    # Validate pickup point if provided
    if ride_data.pickup_point and ride_data.pickup_point not in PICKUP_POINTS:
        raise HTTPException(status_code=400, detail="Invalid pickup point")
    
    ride_id = str(uuid.uuid4())
    ride = {
        "id": ride_id,
        "driver_id": user["id"],
        "driver_name": user["name"],
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
        "status": "posted",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    
    await db.rides.insert_one(ride)
    
    # Generate recurring rides if enabled
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
    limit: int = 20,
    offset: int = 0
):
    # Build query
    query = {
        "status": "posted",
        "available_seats": {"$gt": 0},
        "departure_time": {"$gte": datetime.now(timezone.utc)}
    }
    
    # Time window filtering
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
    
    # Get all matching rides
    cursor = db.rides.find(query).sort("departure_time", 1).skip(offset).limit(limit)
    rides = await cursor.to_list(length=limit)
    
    # Calculate recommendation scores if search criteria provided
    if source or destination:
        for ride in rides:
            ride["recommendation_score"] = calculate_route_similarity(
                ride["source"], ride["destination"],
                source or "", destination or ""
            )
        # Sort by recommendation score first, then by departure time
        rides.sort(key=lambda x: (-x.get("recommendation_score", 0), x["departure_time"]))
    else:
        for ride in rides:
            ride["recommendation_score"] = 0
    
    # Calculate cost per rider and format response with driver trust info
    formatted_rides = []
    for ride in rides:
        occupied = ride["total_seats"] - ride["available_seats"]
        cost_per_rider = ride["estimated_cost"] / max(occupied, 1)
        
        # Get driver trust info
        driver_trust = await get_user_trust_info(ride["driver_id"])
        
        formatted_rides.append({
            "id": ride["id"],
            "driverId": ride["driver_id"],
            "driverName": ride["driver_name"],
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
    
    # Get driver trust info
    driver_trust = await get_user_trust_info(ride["driver_id"])
    
    # Get safe completion status
    safe_completion = await db.safe_completions.find_one({"ride_id": ride_id})
    
    # Get accepted riders
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
    
    return {
        "id": ride["id"],
        "driverId": ride["driver_id"],
        "driverName": ride["driver_name"],
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
    
    formatted_rides = []
    for ride in rides:
        occupied = ride["total_seats"] - ride["available_seats"]
        cost_per_rider = ride["estimated_cost"] / max(occupied, 1)
        
        # Check for pending ratings
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
    
    # Check if ride exists
    ride = await db.rides.find_one({"id": request_data.ride_id})
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    if ride["available_seats"] <= 0:
        raise HTTPException(status_code=400, detail="No available seats")
    
    # Check if urgent request is within active time window (2 hours)
    if request_data.is_urgent:
        time_until_departure = (ride["departure_time"] - datetime.now(timezone.utc)).total_seconds() / 3600
        if time_until_departure > 2:
            raise HTTPException(
                status_code=400, 
                detail="Urgent requests are only allowed for rides departing within 2 hours"
            )
    
    # Check if already requested
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
    
    # Verify ride belongs to driver
    ride = await db.rides.find_one({"id": ride_id})
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    if ride["driver_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get requests, urgent ones first
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
    
    # Fetch associated rides
    result = []
    for req in requests:
        ride = await db.rides.find_one({"id": req["ride_id"]})
        if ride:
            # Check for pending rating (rider rates driver)
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
            
            # Check safe completion
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
    
    # Update request status
    await db.ride_requests.update_one(
        {"id": request_id},
        {"$set": {"status": "accepted", "updated_at": datetime.now(timezone.utc)}}
    )
    
    # Decrease available seats
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
    
    # Verify ride exists and is completed
    ride = await db.rides.find_one({"id": rating_data.ride_id})
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    if ride["status"] != "completed":
        raise HTTPException(status_code=400, detail="Can only rate completed rides")
    
    # Verify user was part of this ride
    is_driver = ride["driver_id"] == user["id"]
    is_rider = await db.ride_requests.find_one({
        "ride_id": rating_data.ride_id,
        "rider_id": user["id"],
        "status": "accepted"
    })
    
    if not is_driver and not is_rider:
        raise HTTPException(status_code=403, detail="You were not part of this ride")
    
    # Verify rated user was part of ride
    rated_is_driver = ride["driver_id"] == rating_data.rated_user_id
    rated_is_rider = await db.ride_requests.find_one({
        "ride_id": rating_data.ride_id,
        "rider_id": rating_data.rated_user_id,
        "status": "accepted"
    })
    
    if not rated_is_driver and not rated_is_rider:
        raise HTTPException(status_code=400, detail="Rated user was not part of this ride")
    
    # Can't rate yourself
    if user["id"] == rating_data.rated_user_id:
        raise HTTPException(status_code=400, detail="Cannot rate yourself")
    
    # Check for existing rating
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
    """Get aggregated rating info for a user (no individual feedback exposed)"""
    pipeline = [
        {"$match": {"rated_user_id": user_id}},
        {"$group": {
            "_id": None,
            "avgRating": {"$avg": "$rating"},
            "count": {"$sum": 1},
            "stars": {
                "$push": "$rating"
            }
        }}
    ]
    result = await db.ratings.aggregate(pipeline).to_list(1)
    
    if not result:
        return {
            "avgRating": 0,
            "totalRatings": 0,
            "distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        }
    
    # Calculate distribution
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
    
    # Verify ride exists
    ride = await db.rides.find_one({"id": data.ride_id})
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    # Only riders can confirm safe completion
    ride_request = await db.ride_requests.find_one({
        "ride_id": data.ride_id,
        "rider_id": user["id"],
        "status": "accepted"
    })
    if not ride_request:
        raise HTTPException(status_code=403, detail="Only accepted riders can confirm safe completion")
    
    # Check if already confirmed
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
    
    # Get all completed and cancelled rides
    cursor = db.rides.find({
        "driver_id": user["id"],
        "status": {"$in": ["completed", "cancelled"]}
    }).sort("departure_time", -1)
    rides = await cursor.to_list(length=100)
    
    history = []
    for ride in rides:
        # Get accepted riders
        accepted_requests = await db.ride_requests.find({
            "ride_id": ride["id"],
            "status": "accepted"
        }).to_list(100)
        
        riders_count = len(accepted_requests)
        actual_cost = ride["estimated_cost"] / max(riders_count, 1) if riders_count > 0 else ride["estimated_cost"]
        
        # Get safe completions
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
            "role": "driver"
        })
    
    return {"history": history}

@app.get("/api/history/rider")
async def get_rider_history(authorization: str = None):
    user = await get_current_user(authorization)
    
    # Get all accepted requests where ride is completed or cancelled
    cursor = db.ride_requests.find({
        "rider_id": user["id"],
        "status": "accepted"
    }).sort("created_at", -1)
    requests = await cursor.to_list(length=100)
    
    history = []
    for req in requests:
        ride = await db.rides.find_one({"id": req["ride_id"]})
        if ride and ride["status"] in ["completed", "cancelled"]:
            # Calculate cost
            accepted_count = await db.ride_requests.count_documents({
                "ride_id": ride["id"],
                "status": "accepted"
            })
            cost_per_rider = ride["estimated_cost"] / max(accepted_count, 1)
            
            # Check safe completion
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
    
    return {
        "totalUsers": total_users,
        "totalRides": total_rides,
        "totalRequests": total_requests,
        "activeRides": active_rides,
        "completedRides": completed_rides,
        "urgentPendingRequests": urgent_requests,
        "totalRatings": total_ratings,
        "safeCompletions": safe_completions
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
