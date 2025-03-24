# simulation/simulation.py (updated code)
import time
import random
import json
import os
import sys
from kafka import KafkaProducer
from kafka.errors import KafkaError
import redis  # Import Redis

def create_producer(retries=5):
    KAFKA_BROKER = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
    print(f"Attempting to connect to Kafka at {KAFKA_BROKER}")
    
    for attempt in range(retries):
        try:
            producer = KafkaProducer(
                bootstrap_servers=[KAFKA_BROKER],
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',
                retries=5,
                retry_backoff_ms=1000,
                request_timeout_ms=30000,
                max_block_ms=30000
            )
            print(f"Successfully connected to Kafka at {KAFKA_BROKER}")
            return producer
        except Exception as e:
            print(f"Attempt {attempt + 1}/{retries} failed: {str(e)}")
            if attempt < retries - 1:
                print("Retrying in 5 seconds...")
                time.sleep(5)
            else:
                print("Failed to connect to Kafka after all attempts")
                raise

TOPIC = "robot-positions"

class Robot:
    def __init__(self, robot_id, x=0, y=0):
        self.robot_id = robot_id
        # Initialize position within screen bounds (0-100 for both x and y)
        self.position = {
            "x": random.randint(0, 100) if x == 0 else min(100, max(0, x)),
            "y": random.randint(0, 100) if y == 0 else min(100, max(0, y))
        }
        self.battery = random.uniform(80, 100)
        self.status = "active"
        self.current_task = None
        self.charging = False
        self.error = None  # Initialize error field
        
        # Add connection retry logic for Redis
        self.redis_client = None
        self._connect_to_redis(retries=3)
        
    def _connect_to_redis(self, retries=3):
        """Establish connection to Redis with retry logic"""
        redis_host = os.getenv('REDIS_HOST', 'redis')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        
        for attempt in range(retries):
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    decode_responses=True,
                    socket_timeout=5
                )
                # Test connection
                self.redis_client.ping()
                print(f"Robot {self.robot_id} connected to Redis at {redis_host}:{redis_port}")
                return
            except (redis.ConnectionError, redis.TimeoutError) as e:
                print(f"Robot {self.robot_id}: Redis connection attempt {attempt+1}/{retries} failed: {str(e)}")
                if attempt < retries - 1:
                    time.sleep(2)
                else:
                    print(f"Robot {self.robot_id}: Failed to connect to Redis after {retries} attempts")
                    # Initialize in offline mode
                    self.error = "Redis connection failed"

    def move(self):
        # Check Redis for task assignments
        redis_data = None
        
        # Handle case where Redis connection failed in init
        if not self.redis_client:
            # Try to reconnect if we don't have a connection
            self._connect_to_redis(retries=1)
            if not self.redis_client:
                # Still no connection, continue with existing state
                pass
        
        if self.redis_client:
            try:
                redis_data = self.redis_client.get(f"robot:{self.robot_id}")
                if redis_data:
                    try:
                        status_data = json.loads(redis_data)
                        # Validate required fields exist in data
                        self.current_task = status_data.get("current_task")
                        self.charging = status_data.get("charging", False)
                        
                        # Preserve charging status priority
                        if self.charging:
                            self.status = "charging"
                        else:
                            self.status = status_data.get("status", "active")
                    except json.JSONDecodeError as e:
                        print(f"Robot {self.robot_id}: Invalid JSON data in Redis: {str(e)}")
            except Exception as e:
                print(f"Robot {self.robot_id}: Error checking Redis for tasks: {str(e)}")
                # Try to reconnect next time
                self.redis_client = None
        
        # Add movement logic
        # Only move if battery is above 0 and not charging and in appropriate status
        if self.status in ["busy"] and self.battery > 0 and not self.charging:
            # Random movement within bounds (0-100)
            self.position["x"] = max(0, min(100, self.position["x"] + random.uniform(-2, 2)))
            self.position["y"] = max(0, min(100, self.position["y"] + random.uniform(-2, 2)))

        # Battery logic
        if self.charging:
            self.battery = min(100.0, self.battery + 1.0)  # Charge 1%/sec
            if self.battery >= 100:
                self.charging = False
                self.status = "busy" if self.current_task else "active"
                self.error = None  # Clear errors
                
                # Update Redis to reflect charging completion
                if self.redis_client:
                    try:
                        self.redis_client.set(
                            f"robot:{self.robot_id}",
                            json.dumps({
                                "status": "busy" if self.current_task else "active",
                                "charging": False,
                                "battery": 100.0,
                                "position": self.position,
                                "current_task": self.current_task,
                                "error": None
                            })
                        )
                    except Exception as e:
                        print(f"Robot {self.robot_id}: Error updating Redis: {str(e)}")
                        self.redis_client = None  # Reset connection for next attempt

                # Publish final status to Kafka
                final_status = {
                    "id": self.robot_id,
                    "status": "busy" if self.current_task else "active",
                    "charging": False,
                    "battery": 100.0
                }
                return final_status  # Return final status for publishing
        else:
            if self.status in ["active", "busy"]:
                # Handle case where battery is already 0
                if self.battery <= 0:
                    self.battery = 0
                    self.status = "error"
                    self.error = "Battery depleted"
                else:
                    self.battery -= random.uniform(0.2, 0.5)
                    if self.battery < 0:
                        self.battery = 0
                        self.status = "error"
                        self.error = "Battery depleted"

        # Low battery warning (only when not charging)
        if not self.charging and 0 < self.battery < 30:
            self.error = "Low battery warning"
        elif self.charging:
            self.error = None  # Clear warnings during charging
        elif self.battery <= 0:
            self.error = "Battery depleted"

        return None  # No final status to publish

    def getstatus(self):
        return {
            "id": self.robot_id,
            "status": "busy" if self.current_task and not self.charging else self.status,
            "position": self.position,
            "battery": round(self.battery, 1),
            "current_task": self.current_task,
            "error": self.error,
            "charging": self.charging
        }

def simulate_robots(num_robots=5):
    # Handle invalid number of robots
    if num_robots <= 0:
        print("Error: Number of robots must be greater than 0")
        return
        
    try:
        producer = create_producer()
    except Exception as e:
        print(f"Failed to create Kafka producer: {str(e)}")
        print("Simulation cannot start without Kafka connection")
        return
        
    robots = [Robot(robot_id=i) for i in range(num_robots)]
    
    print(f"Starting simulation with {num_robots} robots")
    while True:
        try:
            for robot in robots:
                final_status = robot.move()  # Update robot state
                status = robot.getstatus()
                
                # Publish final status if charging completed
                if final_status:
                    try:
                        producer.send(TOPIC, final_status)
                        print(f"Published final status: {final_status}")
                    except Exception as e:
                        print(f"Failed to publish final status: {str(e)}")
                
                # Publish regular status with more robust error handling
                try:
                    future = producer.send(TOPIC, status)
                    try:
                        record_metadata = future.get(timeout=10)
                        print(f"Published: {status} to partition {record_metadata.partition} at offset {record_metadata.offset}")
                    except KafkaError as e:
                        print(f"Failed to send message: {str(e)}")
                except Exception as e:
                    print(f"Error publishing to Kafka: {str(e)}")
                    # Try to reconnect producer
                    try:
                        producer = create_producer()
                    except Exception as reconnect_error:
                        print(f"Failed to reconnect to Kafka: {str(reconnect_error)}")
            
            try:
                producer.flush()
            except Exception as e:
                print(f"Error flushing messages: {str(e)}")
                # Try to reconnect producer
                try:
                    producer = create_producer()
                except Exception as reconnect_error:
                    print(f"Failed to reconnect to Kafka: {str(reconnect_error)}")
                    
            time.sleep(1)  # Simulate every second
            
        except Exception as e:
            print(f"Error in simulation loop: {str(e)}")
            time.sleep(1)




if __name__ == '__main__':
    try:
        simulate_robots()
    except KeyboardInterrupt:
        print("Shutting down simulation...")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        sys.exit(1)