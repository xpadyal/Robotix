# Warehouse Robot Fleet Dashboard

A comprehensive real-time monitoring and control system for warehouse robots, featuring both a RESTful API backend and an interactive web-based dashboard.

## Features

### Backend
- RESTful API endpoints for robot status monitoring
- Redis integration for real-time status updates
- Automatic API documentation
- Docker support

### Frontend Dashboard
- Real-time robot status monitoring
- Interactive warehouse map showing robot positions
- Battery level monitoring with visual indicators
- Task assignment and management
- System health monitoring
- Charging control for robots
- Responsive design for desktop and mobile use

## Key Technologies

- **Kafka**: Message broker for handling robot telemetry data and ensuring reliable communication between robots and the backend
- **Redis**: In-memory data store for caching robot statuses and enabling real-time updates
- **Docker**: Containerization for consistent deployment across different environments
- **Kubernetes (k8s)**: Container orchestration for scaling, load balancing, and managing the deployment in production
- **FastAPI**: High-performance Python web framework for building the backend API
- **JavaScript/CSS/HTML**: Frontend stack for building the interactive dashboard


## Prerequisites

- Python 3.11 or higher
- Redis server
- Kafka server
- Modern web browser (Chrome, Firefox, Safari, Edge)
- Docker and Kubernetes (for containerized deployment)

## Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the Application

### Local Development

```bash
python main.py
```

The server will start at http://localhost:8080

### Using Docker

1. Build the Docker image:
```bash
docker build -t robot-dashboard .
```

2. Run the container:
```bash
docker run -p 8080:8080 robot-dashboard
```

### Kubernetes Deployment

Apply the Kubernetes manifests:

```bash
kubectl apply -f k8/dashboard-deployment.yaml
kubectl apply -f k8/redis-deployment.yaml
kubectl apply -f k8/kafka-deployment.yaml
```

## Dashboard Usage Guide

### Main Dashboard Components

1. **Warehouse Map**: Displays the real-time positions of robots in the warehouse
   - Robot markers are color-coded by status
   - Robots with low battery are highlighted
   - Charging robots display a lightning icon

2. **Robot Status Cards**: Detailed information about each robot
   - Battery level with visual indicator
   - Current status and assigned task
   - Control buttons for charging and task management

3. **Task Control**: Interface for assigning tasks to robots
   - Select robot and task from dropdown menus
   - Safety checks prevent assigning tasks to depleted robots

4. **System Statistics**: Overview of the entire robot fleet
   - Number of active robots
   - Tasks completed
   - System health status based on average battery level
   - Average battery percentage across all robots

### Robot States

Robots can be in the following states:

- **Active**: Ready to accept tasks
- **Busy**: Currently performing a task
- **Charging**: Connected to a charging station
- **Inactive**: Not currently in service
- **Error**: Experiencing a malfunction

### System Health Indicators

The system health is determined by the average battery level of all robots:

- **Good (Green)**: Average battery is 50% or higher
- **Average (Orange)**: Average battery is between 20% and 49.9%
- **Bad (Red)**: Average battery is below 20%

## API Endpoints

- `GET /`: Welcome message
- `GET /robot-status`: Get status of all robots
- `GET /tasks-completed`: Get count of completed tasks
- `POST /control/robot/{robot_id}/charge`: Start or stop charging a robot
- `POST /control/robot/{robot_id}/task`: Assign a task to a robot
- `POST /control/robot/{robot_id}/end-task`: End the current task of a robot
- `GET /health`: Check system health
- `GET /docs`: Interactive API documentation (provided by FastAPI)

## Environment Variables

Create a `.env` file with the following variables (optional):

```
REDIS_HOST=redis
REDIS_PORT=6379
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
K8S_NAMESPACE=robotix
```

## Error Handling

The dashboard includes comprehensive error handling:

- Connection status notifications
- Clear indication of robot errors
- Task assignment validation
- Prominent error messages for critical issues
- Automatic retry for failed API requests

## Browser Compatibility

The dashboard is tested and compatible with:
- Chrome 80+
- Firefox 75+
- Safari 13+
- Edge 80+

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 

