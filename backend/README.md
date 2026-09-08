# FoodBridge Backend

Production-grade FastAPI backend for the FoodBridge food rescue platform.

## Tech Stack
- **FastAPI** (Python) — async REST API + WebSockets
- **PostgreSQL + PostGIS** — geospatial queries
- **Redis** — caching + task queues
- **JWT** — authentication
- **Twilio WhatsApp** — volunteer notifications

## Prerequisites
- Python 3.11+
- PostgreSQL 15+ with PostGIS extension
- Redis 7+

## Setup

### 1. Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env with your database, Redis, and Twilio credentials
```

### 3. Setup PostgreSQL with PostGIS
```sql
CREATE DATABASE foodbridge;
\c foodbridge
CREATE EXTENSION postgis;
```

### 4. Run migrations
```bash
alembic upgrade head
```

### 5. Start the server
```bash
python run.py
# or
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API docs available at: http://localhost:8000/docs

---

## API Endpoints

### Authentication
| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/auth/register` | Public | Register user |
| POST | `/api/v1/auth/login` | Public | Login, get JWT |
| GET | `/api/v1/auth/me` | Any | Get current user |
| PATCH | `/api/v1/auth/availability` | Volunteer | Toggle availability |

### Donations
| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/donations` | Donor/NGO | Create donation (multipart with image) |
| GET | `/api/v1/donations` | Any | List donations |
| GET | `/api/v1/donations/{id}` | Any | Get donation |
| DELETE | `/api/v1/donations/{id}` | Donor/Admin | Cancel donation |

### Food Requests
| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/requests` | Receiver/NGO | Create food request |
| GET | `/api/v1/requests` | Any | List requests |
| DELETE | `/api/v1/requests/{id}` | Receiver/Admin | Cancel request |

### Matching Engine
| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/matching/trigger/{donation_id}` | Admin/NGO | Trigger match for donation |
| POST | `/api/v1/matching/run-all` | Admin | Match all available donations |

### Deliveries & Tracking
| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/deliveries` | Any | List deliveries |
| GET | `/api/v1/deliveries/{id}` | Any | Get delivery |
| POST | `/api/v1/deliveries/{id}/accept` | Volunteer | Accept delivery |
| POST | `/api/v1/deliveries/{id}/pickup` | Volunteer | Mark picked up |
| POST | `/api/v1/deliveries/{id}/deliver` | Volunteer | Mark delivered |
| POST | `/api/v1/deliveries/verify-otp` | Any | Verify delivery OTP |
| POST | `/api/v1/deliveries/webhook/whatsapp` | Twilio | WhatsApp reply webhook |

### Analytics
| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/analytics/summary` | Admin/NGO | Platform stats |
| GET | `/api/v1/analytics/activity-feed` | Admin/NGO/Volunteer | Live activity feed |

### WebSockets
| Endpoint | Description |
|----------|-------------|
| `ws://host/ws?token=JWT` | Global activity feed |
| `ws://host/ws/delivery/{id}?token=JWT` | Per-delivery real-time updates |
| `ws://host/ws/user/{user_id}?token=JWT` | Per-user notifications |

---

## Core Architecture

### Feasibility Check Engine
Every match is validated:
```
estimated_delivery_time < remaining_time_before_expiry
```
- Haversine distance calculation (volunteer→donor→receiver)
- 20% traffic buffer applied to ETA
- Only feasible matches are created

### Smart Matching Algorithm
1. Find open requests within `MAX_MATCHING_RADIUS_KM` using PostGIS `ST_DWithin`
2. Filter by `quantity_serves >= people_count`
3. Sort by urgency (critical→high→medium→low) then proximity
4. Run feasibility check on each candidate
5. Assign nearest available volunteer
6. Create delivery + notify via WhatsApp

### Background Workers
- **Expiry Scanner** (every 60s): marks expired donations, re-queues near-expiry
- **Volunteer Timeout Watcher** (every 30s): reassigns if no response in 5 min
- **Reassignment Worker** (every 5s): processes reassignment queue from Redis

### RBAC Permissions
| Feature | Donor | Receiver | Volunteer | NGO | Admin |
|---------|-------|----------|-----------|-----|-------|
| Create donation | ✅ | ❌ | ❌ | ✅ | ✅ |
| Create request | ❌ | ✅ | ❌ | ✅ | ✅ |
| Accept delivery | ❌ | ❌ | ✅ | ❌ | ❌ |
| Trigger matching | ❌ | ❌ | ❌ | ✅ | ✅ |
| View analytics | ❌ | ❌ | ❌ | ✅ | ✅ |

---

## Frontend Integration

The frontend (`index.html`) connects to this backend:

```javascript
// WebSocket for live activity feed
const ws = new WebSocket(`ws://localhost:8000/ws?token=${jwt}`);
ws.onmessage = (e) => {
  const event = JSON.parse(e.data);
  // Handle: match_created, delivery_completed, food_picked_up, etc.
};

// REST API example
const res = await fetch('http://localhost:8000/api/v1/donations', {
  headers: { Authorization: `Bearer ${jwt}` }
});
```
