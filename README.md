# CampusPool - Campus Ride Sharing Platform

A complete full-stack ride-sharing application for college students, featuring a FastAPI backend and React frontend.

## Project Structure

```
/app/
├── backend/                # FastAPI Backend
│   ├── server.py          # Main FastAPI application with all API routes
│   ├── requirements.txt   # Python dependencies
│   └── .env              # Environment variables (MONGO_URL, JWT_SECRET)
│
├── frontend/              # React Frontend
│   ├── src/
│   │   ├── App.js        # Main React application
│   │   ├── App.css       # Application styles
│   │   ├── index.js      # React entry point
│   │   └── index.css     # Global styles
│   ├── package.json      # Node.js dependencies
│   └── .env              # Frontend environment variables
│
├── campuspool-backend/    # Legacy Node.js backend (deprecated)
└── README.md             # This file
```

## Tech Stack

### Backend (FastAPI)
- **FastAPI** - Modern Python web framework
- **Motor** - Async MongoDB driver
- **Pydantic** - Data validation
- **PyJWT** - JWT authentication
- **bcrypt** - Password hashing
- **MongoDB** - Database

### Frontend (React)
- **React 18** - UI framework
- **Axios** - HTTP client
- **Lucide React** - Icons
- **date-fns** - Date utilities
- **Tailwind CSS** - Styling

## Features

### Authentication & Users
- Email/password signup and login
- JWT-based authentication
- Role-based access (Rider, Driver, Admin)
- User profile management
- Academic info (Branch, Year)
- Trust system with ratings

### Ride Management
- **Drivers**: Post rides with route, time, seats, cost
- **Riders**: Browse, search, and request rides
- Event-based rides (Exams, Fests, etc.)
- Recurring rides (Daily, Weekly, Weekdays)
- Pickup point selection
- Smart route matching

### Safety & Trust
- User ratings (1-5 stars)
- Trust labels (New User, Regular, Trusted)
- Safe completion confirmation
- SOS/Emergency events
- User reporting system

### Admin Panel
- User management (verify, suspend, disable)
- SOS event handling
- Report moderation
- Analytics dashboard
- Audit logging

### Gamification
- Achievement badges
- Ride streaks
- Eco impact tracking (CO2 saved)
- Cost savings calculation

## API Endpoints

### Authentication
- `POST /api/auth/signup` - Register new user
- `POST /api/auth/login` - User login
- `GET /api/auth/me` - Get current user info
- `PATCH /api/auth/profile` - Update profile

### Rides
- `GET /api/rides` - List available rides (with filters)
- `GET /api/rides/{id}` - Get ride details
- `POST /api/rides` - Post new ride (driver)
- `PATCH /api/rides/{id}/status` - Update ride status
- `GET /api/rides/driver/my-rides` - Get driver's rides

### Ride Requests
- `POST /api/requests` - Request a ride (rider)
- `GET /api/requests/ride/{id}` - Get requests for a ride
- `GET /api/requests/my-requests` - Get user's requests
- `PATCH /api/requests/{id}/accept` - Accept request (driver)
- `PATCH /api/requests/{id}/reject` - Reject request (driver)

### Ratings & Safety
- `POST /api/ratings` - Submit rating
- `GET /api/ratings/user/{id}` - Get user ratings
- `POST /api/safe-completion` - Confirm safe arrival
- `POST /api/sos` - Create emergency event
- `POST /api/reports` - Submit report

### Admin (Requires Admin Role)
- `GET /api/admin/users` - List all users
- `GET /api/admin/users/{id}` - Get user details
- `POST /api/admin/users/{id}/action` - Take action on user
- `POST /api/admin/users/{id}/verify` - Verify/revoke user
- `GET /api/admin/sos` - List SOS events
- `GET /api/admin/reports` - List reports
- `GET /api/admin/analytics` - System analytics
- `GET /api/admin/audit-logs` - Admin audit logs

### Utility
- `GET /api/health` - Health check
- `GET /api/pickup-points` - Get pickup locations
- `GET /api/event-tags` - Get event categories
- `GET /api/academic-options` - Get branch/year options

## Environment Variables

### Backend (.env)
```
MONGO_URL=mongodb://localhost:27017
JWT_SECRET=your_secret_key
```

### Frontend (.env)
```
REACT_APP_BACKEND_URL=http://localhost:8001
```

## Development

### Prerequisites
- Python 3.11+
- Node.js 18+
- MongoDB

### Backend Setup
```bash
cd /app/backend
pip install -r requirements.txt
# Backend runs via supervisor on port 8001
```

### Frontend Setup
```bash
cd /app/frontend
yarn install
# Frontend runs via supervisor on port 3000
```

### Services Management
```bash
# Check status
sudo supervisorctl status

# Restart services
sudo supervisorctl restart backend
sudo supervisorctl restart frontend
sudo supervisorctl restart all
```

## User Roles

### Rider
- Browse and search rides
- Send ride requests
- Rate drivers after rides
- Confirm safe arrival
- View ride history

### Driver
- Post rides with details
- Accept/reject ride requests
- Mark rides as completed
- Rate riders after rides
- Manage recurring rides

### Admin
- Manage all users
- Handle SOS emergencies
- Review and resolve reports
- View system analytics
- Create custom event tags

## Eco Impact Tracking

The platform calculates environmental impact:
- **CO2 Saved**: 0.21 kg/km × 50% reduction for shared rides
- **Trees Equivalent**: CO2 saved ÷ 21 kg/year per tree
- **Cost Savings**: Comparison vs. solo travel

## Trust System

Users earn trust levels based on:
- **New User**: < 3 completed rides
- **Low Rating**: Average rating < 3.0
- **Regular**: 3+ rides, decent ratings
- **Trusted**: 10+ rides, rating ≥ 4.5

## License

MIT License
