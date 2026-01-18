from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime, timedelta
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
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(authorization: str = None):
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
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
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
async def get_current_user_info(authorization: str = None):
    user = await get_current_user(authorization)
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"]
    }

# Rides Routes
@app.post("/api/rides")
async def create_ride(ride_data: RideCreate, authorization: str = None):
    user = await get_current_user(authorization)
    
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
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
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
        "departure_time": {"$gte": datetime.utcnow()}
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
    
    # Calculate cost per rider and format response
    formatted_rides = []
    for ride in rides:
        occupied = ride["total_seats"] - ride["available_seats"]
        cost_per_rider = ride["estimated_cost"] / max(occupied, 1)
        
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
    
    return {
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
        "status": ride["status"]
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
            "status": ride["status"]
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
        {"$set": {"status": status, "updated_at": datetime.utcnow()}}
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
        time_until_departure = (ride["departure_time"] - datetime.utcnow()).total_seconds() / 3600
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
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
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
    
    return {
        "requests": [{
            "id": req["id"],
            "rideId": req["ride_id"],
            "riderId": req["rider_id"],
            "riderName": req["rider_name"],
            "isUrgent": req.get("is_urgent", False),
            "status": req["status"],
            "createdAt": req["created_at"].isoformat()
        } for req in requests]
    }

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
                    "pickupPoint": ride.get("pickup_point")
                }
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
        {"$set": {"status": "accepted", "updated_at": datetime.utcnow()}}
    )
    
    # Decrease available seats
    await db.rides.update_one(
        {"id": request["ride_id"]},
        {"$inc": {"available_seats": -1}, "$set": {"updated_at": datetime.utcnow()}}
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
        {"$set": {"status": "rejected", "updated_at": datetime.utcnow()}}
    )
    
    return {"message": "Request rejected successfully"}

# Admin/Stats Routes
@app.get("/api/stats")
async def get_stats(authorization: str = None):
    user = await get_current_user(authorization)
    
    total_users = await db.users.count_documents({})
    total_rides = await db.rides.count_documents({})
    total_requests = await db.ride_requests.count_documents({})
    active_rides = await db.rides.count_documents({"status": "posted"})
    urgent_requests = await db.ride_requests.count_documents({"is_urgent": True, "status": "pending"})
    
    return {
        "totalUsers": total_users,
        "totalRides": total_rides,
        "totalRequests": total_requests,
        "activeRides": active_rides,
        "urgentPendingRequests": urgent_requests
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
