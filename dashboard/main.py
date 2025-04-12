from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from redis.exceptions import RedisError
from typing import List, Dict, Optional
import json
import asyncio
import os
import time
from pydantic import BaseModel
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Load environment variables
load_dotenv()

# Define data models
class RobotStatus(BaseModel):
    id: int
    status: str
    position: Dict[str, float]
    battery: float
    current_task: Optional[str] = None
    error: Optional[str] = None
    timestamp: Optional[float] = None

class TaskAssignment(BaseModel):
    task: str

class ChargeCommand(BaseModel):
    charge: bool

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Robot Dashboard API")

# Add rate limit error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add rate limit middleware
app.add_middleware(SlowAPIMiddleware)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# Setup static files
app.mount("/static", StaticFiles(directory="static"), name="static")

def get_redis() -> Redis:
    return Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_timeout=5)

def increment_completed_tasks():
    redis_client = get_redis()
    try:
        return redis_client.incr("tasks:completed")
    except RedisError as e:
        print(f"Error incrementing tasks: {str(e)}")
    finally:
        redis_client.close()

def get_completed_tasks():
    redis_client = get_redis()
    try:
        return int(redis_client.get("tasks:completed") or 0)
    except RedisError as e:
        print(f"Error getting tasks: {str(e)}")
        return 0
    finally:
        redis_client.close()

async def auto_end_task(robot_id: int):
    await asyncio.sleep(60)  # Wait 1 minute
    redis_client = get_redis()
    try:
        redis_key = f"robot:{robot_id}"
        data = redis_client.get(redis_key)
        if data and json.loads(data).get("current_task"):
            redis_client.set(redis_key, json.dumps({
                **json.loads(data),
                "current_task": None,
                "status": "active"
            }))
            increment_completed_tasks()
    finally:
        redis_client.close()

@app.get("/", response_class=HTMLResponse)
@limiter.limit("60/minute")
async def get_dashboard(request: Request):
    try:
        path = os.path.join(os.path.dirname(__file__), "static", "index.html")
        print(f"Looking for index.html at: {path}")
        
        if not os.path.exists(path):
            print(f"File not found! Searching in current directory instead")
            path = "static/index.html"
            
        with open(path) as f:
            return f.read()
    except Exception as e:
        print(f"Error serving index.html: {str(e)}")
        return HTMLResponse(
            content=f"""
            <html>
                <head><title>Robot Dashboard</title></head>
                <body>
                    <h1>Robot Dashboard</h1>
                    <p>Error loading dashboard: {str(e)}</p>
                    <p>Please check the server logs for more information.</p>
                    <p>API endpoints:</p>
                    <ul>
                        <li><a href="/api/test">/api/test</a> - Test API connectivity</li>
                        <li><a href="/api/health">/api/health</a> - Check system health</li>
                        <li><a href="/api/debug">/api/debug</a> - Debug information</li>
                        <li><a href="/api/robot-status">/api/robot-status</a> - Robot status data</li>
                    </ul>
                </body>
            </html>
            """,
            status_code=500
        )

@app.get("/api/test")
@limiter.limit("30/minute")
async def test_endpoint(request: Request):
    """Simple test endpoint to verify API is working"""
    return {"status": "ok", "message": "API is working"}

@app.get("/api/tasks-completed")
@limiter.limit("30/minute")
async def get_completed_tasks_count(request: Request):
    return {"tasks_completed": get_completed_tasks()}

@app.get("/api/debug")
@limiter.limit("10/minute")
async def debug_info(request: Request):
    """Debug endpoint to help diagnose connectivity issues"""
    return {
        "server_info": {
            "host": os.getenv("HOST", "0.0.0.0"),
            "port": int(os.getenv("PORT", "8080")),
            "redis_config": {
                "host": REDIS_HOST,
                "port": REDIS_PORT,
            },
            "timestamp": time.time()
        }
    }

@app.get("/api/health")
@limiter.limit("60/minute")
async def health_check(request: Request):
    """Health check endpoint to verify Redis connection"""
    redis_client = None
    try:
        print(f"Attempting to connect to Redis at {REDIS_HOST}:{REDIS_PORT}")
        redis_client = get_redis()
        redis_client.ping()
        return {"status": "healthy", "redis": "connected"}
    except Exception as e:
        error_message = str(e)
        print(f"Redis health check failed: {error_message}")
        return {
            "status": "unhealthy", 
            "redis": "disconnected", 
            "error": error_message
        }
    finally:
        if redis_client:
            try:
                redis_client.close()
            except Exception as e:
                print(f"Error closing Redis connection: {str(e)}")

@app.get("/api/robot-status", response_model=List[RobotStatus])
@limiter.limit("120/minute")
async def get_robot_status(request: Request):
    redis_client = None
    try:
        redis_client = get_redis()
        statuses = []
        for robot_id in range(5):  # Assuming 5 robots
            try:
                status_data = redis_client.get(f"robot:{robot_id}")
                if status_data:
                    robot_data = json.loads(status_data)
                    
                    # Remove 'id' from the data if present
                    robot_data.pop('id', None)
                    
                    statuses.append(RobotStatus(id=robot_id, **robot_data))
                else:
                    # Generate placeholder data
                    statuses.append(RobotStatus(
                        id=robot_id,
                        status="inactive",
                        position={"x": 0, "y": 0},
                        battery=100.0,
                        timestamp=time.time()
                    ))
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                print(f"Invalid data for robot {robot_id}: {str(e)}")
                statuses.append(RobotStatus(
                    id=robot_id,
                    status="error",
                    position={"x": 0, "y": 0},
                    battery=0.0,
                    error=f"Data error: {str(e)}",
                    timestamp=time.time()
                ))
        return statuses
    except RedisError as e:
        error_message = f"Redis error: {str(e)}"
        print(f"DETAILED ERROR: {error_message}")
        return [RobotStatus(
            id=i,
            status="error",
            position={"x": 0, "y": 0},
            battery=0.0,
            error=error_message,
            timestamp=time.time()
        ) for i in range(5)]
    finally:
        if redis_client:
            redis_client.close()
            
@app.post("/api/control/robot/{robot_id}/task")
@limiter.limit("30/minute")
async def assign_task(request: Request, robot_id: int, task: TaskAssignment):
    redis_client = None
    try:
        redis_client = get_redis()
        redis_key = f"robot:{robot_id}"
        
        # Get existing data
        existing_data = {}
        if redis_client.exists(redis_key):
            existing_data = json.loads(redis_client.get(redis_key))
        
        # Merge with new task data
        updated_data = {
            **existing_data,
            "current_task": task.task,
            "status": "busy" if task.task else "active",
            "timestamp": time.time()
        }
        
        # If assigning a new task, clear charging status
        if task.task:
            updated_data["charging"] = False

        redis_client.set(redis_key, json.dumps(updated_data))
        
        # Start auto-completion timer only for new tasks
        if task.task:
            asyncio.create_task(auto_end_task(robot_id))
        
        return {"message": f"Task '{task.task}' assigned to robot {robot_id}"}
    except RedisError as e:
        return JSONResponse(
            status_code=500,
            content={"detail": f"Redis error: {str(e)}"}
        )
    finally:
        if redis_client:
            redis_client.close()

@app.post("/api/control/robot/{robot_id}/charge")
@limiter.limit("30/minute")
async def charge_robot(request: Request, robot_id: int, cmd: ChargeCommand):
    redis_client = None
    try:
        redis_client = get_redis()
        redis_key = f"robot:{robot_id}"
        
        # Get existing data
        existing_data = {}
        existing_data_str = redis_client.get(redis_key)
        if existing_data_str:
            existing_data = json.loads(existing_data_str)
        
        # Update charging status
        updated_data = {
            **existing_data,
            "charging": cmd.charge,
            "status": "charging" if cmd.charge else "inactive"
        }
        
        redis_client.set(redis_key, json.dumps(updated_data))
        return {"message": f"Charging {'started' if cmd.charge else 'stopped'} for robot {robot_id}"}
    
    except RedisError as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})
    finally:
        if redis_client:
            redis_client.close()

@app.post("/api/control/robot/{robot_id}/end-task")
@limiter.limit("30/minute")
async def end_task(request: Request, robot_id: int):
    redis_client = None
    try:
        redis_client = get_redis()
        redis_key = f"robot:{robot_id}"
        
        if not redis_client.exists(redis_key):
            raise HTTPException(status_code=404, detail="Robot not found")
            
        robot_data = json.loads(redis_client.get(redis_key))
        update_data = {
            "current_task": None,
            "status": "active" if not robot_data.get("charging") else "charging",
            "timestamp": time.time()
        }
        
        redis_client.set(redis_key, json.dumps({**robot_data, **update_data}))
        increment_completed_tasks()
        
        return {"message": f"Task ended for robot {robot_id}"}
    except RedisError as e:
        return JSONResponse(
            status_code=500,
            content={"detail": f"Redis error: {str(e)}"}
        )
    finally:
        if redis_client:
            redis_client.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)