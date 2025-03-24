# simulation/consumer.py (updated)
import json
import os
import sys
import time
import signal
from kafka import KafkaConsumer
from kafka.errors import KafkaError, KafkaTimeoutError
import redis
from redis.exceptions import RedisError
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('robot-consumer')

# Global flag for shutdown
running = True

def signal_handler(sig, frame):
    global running
    logger.info("Shutdown signal received, closing gracefully...")
    running = False

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def create_kafka_consumer(retries=5):
    KAFKA_BROKER = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
    logger.info(f"Attempting to connect to Kafka at {KAFKA_BROKER}")
    
    for attempt in range(retries):
        try:
            consumer = KafkaConsumer(
                "robot-positions",
                bootstrap_servers=[KAFKA_BROKER],
                auto_offset_reset='earliest',
                enable_auto_commit=True,
                group_id='robot-group',
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                session_timeout_ms=30000,
                heartbeat_interval_ms=10000,
                # Add error tolerance
                max_poll_interval_ms=300000,
                request_timeout_ms=305000
            )
            logger.info(f"Successfully connected to Kafka at {KAFKA_BROKER}")
            return consumer
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}/{retries} to connect to Kafka failed: {str(e)}")
            if attempt < retries - 1:
                logger.info("Retrying in 5 seconds...")
                time.sleep(5)
            else:
                logger.error("Failed to connect to Kafka after all attempts")
                raise

def create_redis_client(retries=5):
    REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    logger.info(f"Attempting to connect to Redis at {REDIS_HOST}:{REDIS_PORT}")
    
    for attempt in range(retries):
        try:
            client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=0,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                health_check_interval=30  # Enable health checks
            )
            client.ping()
            logger.info(f"Successfully connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
            return client
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}/{retries} to connect to Redis failed: {str(e)}")
            if attempt < retries - 1:
                logger.info("Retrying in 5 seconds...")
                time.sleep(5)
            else:
                logger.error("Failed to connect to Redis after all attempts")
                raise

def validate_robot_data(status):
    """Validate robot data structure and normalize types"""
    if not isinstance(status, dict):
        return None, "Message is not a dictionary"
    
    robot_id = status.get('id')
    if robot_id is None:
        return None, "Missing robot ID in message"
    
    # Type conversion and validation for numeric fields
    try:
        # Process battery value
        if 'battery' in status:
            try:
                status['battery'] = float(status['battery'])
                status['battery'] = max(0.0, min(100.0, status['battery']))  # Ensure valid range
            except (ValueError, TypeError):
                status['battery'] = None
                logger.warning(f"Invalid battery value for robot {robot_id}: {status.get('battery')}")

        # Process position values
        if 'position' in status and isinstance(status['position'], dict):
            for coord in ['x', 'y']:
                if coord in status['position']:
                    try:
                        status['position'][coord] = float(status['position'][coord])
                        # Ensure coordinates are in valid range
                        status['position'][coord] = max(0.0, min(100.0, status['position'][coord]))
                    except (ValueError, TypeError):
                        status['position'][coord] = 0.0
                        logger.warning(f"Invalid position {coord} for robot {robot_id}: {status['position'].get(coord)}")
        
        # Validate status field
        if 'status' in status:
            valid_statuses = ['active', 'busy', 'error', 'charging']
            if status['status'] not in valid_statuses:
                logger.warning(f"Invalid status '{status['status']}' for robot {robot_id}, defaulting to 'active'")
                status['status'] = 'active'
                
        # Validate boolean fields
        for bool_field in ['charging']:
            if bool_field in status:
                status[bool_field] = bool(status[bool_field])
    
    except Exception as e:
        logger.error(f"Error validating robot {robot_id} data: {str(e)}")
        return None, f"Validation error: {str(e)}"
        
    return status, None

def update_redis_with_retry(redis_client, key, data, max_retries=3):
    """Update Redis with retry logic"""
    for attempt in range(max_retries):
        try:
            # Check Redis connection
            if not redis_client.ping():
                raise RedisError("Redis connection lost")
                
            # Serialize and store data
            redis_client.set(key, json.dumps(data))
            return True
        except RedisError as e:
            logger.error(f"Redis error on attempt {attempt+1}/{max_retries}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(1)  # Short delay before retry
            else:
                logger.error(f"Failed to update Redis after {max_retries} attempts")
                return False
    return False

def update_history_with_retry(redis_client, key, data, max_retries=3):
    """Update history with retry logic"""
    for attempt in range(max_retries):
        try:
            history_key = f"{key}:history"
            redis_client.lpush(history_key, json.dumps(data))
            redis_client.ltrim(history_key, 0, 999)  # Keep last 1000 entries
            return True
        except RedisError as e:
            logger.error(f"Redis history error on attempt {attempt+1}/{max_retries}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                logger.error(f"Failed to update history after {max_retries} attempts")
                return False
    return False

def try_reconnect_redis(max_retries=3):
    """Try to reconnect to Redis"""
    for attempt in range(max_retries):
        try:
            return create_redis_client(retries=1)
        except Exception as e:
            logger.error(f"Redis reconnection attempt {attempt+1}/{max_retries} failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2)
    return None

def try_reconnect_kafka(max_retries=3):
    """Try to reconnect to Kafka"""
    for attempt in range(max_retries):
        try:
            return create_kafka_consumer(retries=1)
        except Exception as e:
            logger.error(f"Kafka reconnection attempt {attempt+1}/{max_retries} failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2)
    return None

def process_messages():
    global running
    consumer = None
    redis_client = None
    
    # Initial connections
    try:
        consumer = create_kafka_consumer()
        redis_client = create_redis_client()
    except Exception as e:
        logger.error(f"Failed to initialize connections: {str(e)}")
        return
    
    logger.info("Starting to consume messages...")
    consecutive_errors = 0
    last_successful_time = time.time()
    
    while running:
        try:
            # Check connections health periodically
            current_time = time.time()
            if current_time - last_successful_time > 60:  # 1 minute with no success
                logger.warning("No successful operations in the last minute, checking connections...")
                # Test Redis connection
                try:
                    if redis_client and not redis_client.ping():
                        logger.error("Redis connection failed health check")
                        redis_client = try_reconnect_redis()
                except Exception:
                    logger.error("Redis health check failed")
                    redis_client = try_reconnect_redis()
                
                # For Kafka, we'll rely on the exception handling below
                last_successful_time = current_time  # Reset timer

            # Skip cycle if we don't have both connections
            if not consumer or not redis_client:
                logger.error("Missing connections, attempting to reconnect...")
                if not consumer:
                    consumer = try_reconnect_kafka()
                if not redis_client:
                    redis_client = try_reconnect_redis()
                    
                if not consumer or not redis_client:
                    time.sleep(5)  # Avoid tight loop if connections keep failing
                    continue

            # Poll for messages
            message_batch = consumer.poll(timeout_ms=1000)
            if not message_batch:
                continue
                
            for tp, messages in message_batch.items():
                for message in messages:
                    try:
                        raw_status = message.value
                        logger.debug(f"Received robot data: {raw_status}")
                        
                        # Validate and normalize message
                        status, error = validate_robot_data(raw_status)
                        if error:
                            logger.error(f"Validation error: {error}")
                            continue

                        robot_id = status.get('id')
                        redis_key = f"robot:{robot_id}"
                        
                        # Get existing Redis data
                        existing_data = {}
                        try:
                            existing_data_str = redis_client.get(redis_key)
                            if existing_data_str:
                                existing_data = json.loads(existing_data_str)
                        except json.JSONDecodeError:
                            logger.error(f"Invalid JSON in Redis for robot {robot_id}")
                        except Exception as e:
                            logger.error(f"Error loading existing data: {str(e)}")
                            
                            # Try to reconnect if Redis fails
                            redis_client = try_reconnect_redis()
                            if not redis_client:
                                break  # Skip this batch if reconnection fails

                        # Merge data: existing data + new status + timestamp
                        merged_data = {
                            "current_task": existing_data.get("current_task"),
                            "charging": existing_data.get("charging", False),
                            "error": existing_data.get("error"),
                            **status,  # Kafka data OVERRIDES battery/position/status
                            "timestamp": time.time()
                        }

                        # Set status based on charging state
                        if merged_data.get("charging"):
                            merged_data["status"] = "charging"
                        else:
                            merged_data.setdefault("status", "active")

                        # Apply defaults
                        merged_data.setdefault("position", {"x": 0, "y": 0})
                        merged_data.setdefault("battery", 100.0)

                        # Update Redis and history with retry
                        if update_redis_with_retry(redis_client, redis_key, merged_data):
                            if update_history_with_retry(redis_client, redis_key, merged_data):
                                logger.info(f"Processed robot {robot_id}: status={merged_data['status']}, battery={merged_data['battery']}")
                                consecutive_errors = 0
                                last_successful_time = time.time()
                    
                    except Exception as e:
                        logger.error(f"Processing error: {str(e)}")
                        consecutive_errors += 1
                        
                        # If too many consecutive errors, try to reconnect
                        if consecutive_errors > 10:
                            logger.warning("Too many consecutive errors, attempting reconnections...")
                            try:
                                consumer = create_kafka_consumer()
                                redis_client = create_redis_client()
                                consecutive_errors = 0
                            except Exception as reconnect_error:
                                logger.error(f"Reconnection failed: {str(reconnect_error)}")
            
        except KafkaTimeoutError:
            # Just a timeout, not an error
            pass
        except KafkaError as e:
            logger.error(f"Kafka error: {str(e)}")
            consumer = try_reconnect_kafka()
            time.sleep(1)
        except RedisError as e:
            logger.error(f"Redis error: {str(e)}")
            redis_client = try_reconnect_redis()
            time.sleep(1)
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            consecutive_errors += 1
            time.sleep(1)
    
    # Clean shutdown
    logger.info("Shutting down consumer...")
    if consumer:
        try:
            consumer.close(autocommit=True)
            logger.info("Kafka consumer closed")
        except Exception as e:
            logger.error(f"Error closing Kafka consumer: {str(e)}")
    
    if redis_client:
        try:
            redis_client.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {str(e)}")

if __name__ == '__main__':
    try:
        process_messages()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)
    sys.exit(0)