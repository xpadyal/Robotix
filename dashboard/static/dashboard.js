// dashboard.js
// Data storage and state variables
const robotData = {};
let tasksCompleted = 0;
let pollingActive = true;
let pollingInterval;
let retryCount = 0;
const MAX_RETRIES = 3;
const RETRY_DELAY = 5000;

// Initialize the dashboard
async function initDashboard() {
    displayConnectionStatus('Initializing dashboard...');
    
    // Show loading bar until data is fetched
    showLoadingBar();
    
    // Check server health first
    try {
        const healthResponse = await fetch('/api/health');
        if (!healthResponse.ok) {
            throw new Error(`Health check failed with status: ${healthResponse.status}`);
        }
        const healthData = await healthResponse.json();
        displayConnectionStatus(`Server health: ${healthData.status}`);
    } catch (error) {
        console.error('Error checking server health:', error);
        displayConnectionStatus('Failed to check server health. Retrying...', true);
        setTimeout(initDashboard, RETRY_DELAY);
        return;
    }
    
    // Start regular polling
    startPolling();
    
    // Initialize forms and controls
    initTaskForm();
    initChargeButtons();
    initTaskControls();
}

// Display connection status with improved error handling
function displayConnectionStatus(message, isError = false) {
    const statusDiv = document.getElementById('connection-status') || createStatusDiv();
    if (!statusDiv) return; // Safety check
    
    statusDiv.textContent = message;
    statusDiv.className = `connection-status ${isError ? 'error' : 'info'}`;

    if (!isError) {
        setTimeout(() => {
            if (statusDiv && statusDiv.classList) {
                statusDiv.classList.add('fade-out');
            }
        }, 3000);
    }
}

function createStatusDiv() {
    const div = document.createElement('div');
    div.id = 'connection-status';
    document.body.prepend(div);
    return div;
}

// Fetch robot status from API with improved error handling
async function fetchRobotStatus() {
    try {
        // Fetch both robot statuses and tasks completed in parallel with timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 second timeout

        const [statusResponse, tasksResponse] = await Promise.all([
            fetch('/api/robot-status', { signal: controller.signal }),
            fetch('/api/tasks-completed', { signal: controller.signal })
        ]);
        
        clearTimeout(timeoutId);
        
        if (!statusResponse.ok) throw new Error(`HTTP error: ${statusResponse.status}`);
        if (!tasksResponse.ok) throw new Error(`HTTP error: ${tasksResponse.status}`);
        
        const robots = await statusResponse.json();
        const tasksData = await tasksResponse.json();
        
        // Validate data structure
        if (!Array.isArray(robots) || typeof tasksData.tasks_completed !== 'number') {
            throw new Error('Invalid data format received from server');
        }
        
        // Remove loading bar after first successful data fetch
        hideLoadingBar();
        
        // Update dashboard with both sets of data
        updateDashboard({
            robots: robots,
            tasks_completed: tasksData.tasks_completed
        });
        
        retryCount = 0; // Reset retry count on success
        displayConnectionStatus('Data updated successfully');
        return true;
    } catch (error) {
        console.error('Fetch error:', error);
        
        // Handle retries
        if (retryCount < MAX_RETRIES) {
            retryCount++;
            displayConnectionStatus(`Connection error: ${error.message}. Retrying (${retryCount}/${MAX_RETRIES})...`, true);
            setTimeout(fetchRobotStatus, RETRY_DELAY);
        } else {
            displayConnectionStatus('Maximum retry attempts reached. Please refresh the page.', true);
            stopPolling();
        }
        return false;
    }
}

// Polling control
function startPolling() {
    if (pollingInterval) clearInterval(pollingInterval);
    
    pollingActive = true;
    fetchRobotStatus(); // Immediate first fetch
    
    pollingInterval = setInterval(() => {
        if (!pollingActive) {
            clearInterval(pollingInterval);
            return;
        }
        fetchRobotStatus();
    }, 2000);
}

function stopPolling() {
    pollingActive = false;
    if (pollingInterval) clearInterval(pollingInterval);
}

// Dashboard updates
function updateDashboard(data) {
    if (!data || !data.robots) {
        console.error('Invalid data received in updateDashboard');
        return;
    }

    const robots = data.robots;
    tasksCompleted = data.tasks_completed || 0;
    
    robots.forEach(robot => {
        // Update validation to check for required fields instead of just id
        if (!robot || typeof robot.id !== 'number' || !robot.status || !robot.position || 
            typeof robot.battery !== 'number' || robot.current_task === undefined) {
            console.error('Malformed robot data:', robot);
            return;
        }

        // Validate position object
        if (typeof robot.position.x !== 'number' || typeof robot.position.y !== 'number') {
            console.error('Invalid position data for robot:', robot.id);
            return;
        }

        const prevStatus = robotData[robot.id]?.status;
        const prevTask = robotData[robot.id]?.current_task;
        robotData[robot.id] = robot;

        // Track completed tasks with validation
        if (prevTask && !robot.current_task && prevStatus === 'busy') {
            tasksCompleted = Math.max(0, tasksCompleted + 1);
            displayConnectionStatus(`Robot ${robot.id} completed task: ${prevTask}`);
        }
    });

    updateWarehouseMap();
    updateRobotStatusCards();
    updateSystemStats();
}

function updateWarehouseMap() {
    const map = document.querySelector('.warehouse-layout');
    if (!map) {
        console.error('Warehouse map element not found');
        return;
    }

    Object.values(robotData).forEach(robot => {
        if (!robot || !robot.id) return;
        
        let robotElement = document.getElementById(`robot-${robot.id}`);
        if (!robotElement) {
            robotElement = createRobotElement(robot.id);
        }
        
        if (!robotElement) return;
        
        // Update position and status with bounds checking
        const x = Math.max(0, Math.min(100, robot.position?.x || 0));
        const y = Math.max(0, Math.min(100, robot.position?.y || 0));
        robotElement.style.left = `${x}%`;
        robotElement.style.top = `${y}%`;
        
        const status = robot.status || 'unknown';
        const battery = robot.battery || 0;
        robotElement.className = `robot status-${status} ${battery < 30 ? 'low-battery' : ''}`;
        
        // Charging indicator with null check
        const chargingIndicator = robotElement.querySelector('.charging-indicator') || createChargingIndicator();
        if (chargingIndicator) {
            chargingIndicator.style.display = robot.charging ? 'block' : 'none';
        }
    });
}

function createRobotElement(id) {
    const div = document.createElement('div');
    div.id = `robot-${id}`;
    div.className = 'robot';
    div.innerHTML = `<span class="robot-id">${id}</span>`;
    document.querySelector('.warehouse-layout').appendChild(div);
    return div;
}

function createChargingIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'charging-indicator';
    indicator.textContent = '⚡';
    document.querySelector('.robot').appendChild(indicator);
    return indicator;
}

function updateRobotStatusCards() {
    const container = document.getElementById('robot-status-cards');
    if (!container) {
        console.error('Robot status cards container not found');
        return;
    }

    container.innerHTML = '';
    
    Object.values(robotData).forEach(robot => {
        if (!robot || !robot.id) return;
        
        const card = document.createElement('div');
        card.className = `robot-card ${robot.charging ? 'charging' : ''}`;
        
        // Validate battery level
        const batteryLevel = Math.max(0, Math.min(100, robot.battery || 0));
        
        // Control buttons HTML with improved error handling - REMOVED status check to enable charge buttons
        let controlButtons = `
            <div class="robot-controls">
                <button class="charge-button" data-robot-id="${robot.id}" 
                    data-action="${robot.charging ? 'stop' : 'start'}">
                    ${robot.charging ? 'Stop Charging' : 'Charge Robot'}
                </button>
                ${robot.current_task ? `
                    <button class="end-task-button" data-robot-id="${robot.id}">
                        End Task
                    </button>
                ` : ''}
            </div>
        `;

        card.innerHTML = `
            <div class="robot-header">
                <div class="robot-icon status-${robot.status || 'unknown'} ${batteryLevel < 30 ? 'low-battery' : ''}">
                    ${robot.id}
                    ${robot.charging ? '<div class="charging-indicator">⚡</div>' : ''}
                </div>
                <div class="robot-meta">
                    <h3>Robot ${robot.id}</h3>
                    <p class="status">${formatStatus(robot)}</p>
                </div>
            </div>
            <div class="robot-details">
                <div class="battery-container">
                    <div class="battery-bar" style="width: ${batteryLevel}%"></div>
                    <span class="battery-text ${batteryLevel < 30 ? 'warning' : ''}">
                        ${batteryLevel.toFixed(1)}%
                    </span>
                </div>
                ${robot.error ? `<p class="error">${robot.error}</p>` : ''}
                ${robot.current_task ? `<p class="task">Current Task: ${robot.current_task}</p>` : ''}
            </div>
            ${controlButtons}
        `;
        
        container.appendChild(card);
    });
}

function formatStatus(robot) {
    let status = robot.status.charAt(0).toUpperCase() + robot.status.slice(1);
    if (robot.charging) status += ' (Charging)';
    if (robot.error) status += ` - ${robot.error}`;
    return status;
}

function updateSystemStats() {
    document.getElementById('tasks-completed').textContent = tasksCompleted;
    
    const robots = Object.values(robotData);
    const activeRobots = robots.filter(r => ['active', 'busy'].includes(r.status)).length;
    const avgBattery = robots.reduce((sum, r) => sum + r.battery, 0) / robots.length;
    
    document.getElementById('active-robots').textContent = `${activeRobots}/${robots.length}`;
    document.getElementById('avg-battery').textContent = `${avgBattery.toFixed(1)}%`;
    
    // Get the previous system health state
    const systemHealthElement = document.getElementById('system-health');
    const prevSystemHealth = systemHealthElement.textContent || "Unknown";
    
    // Determine system health based on average battery level
    let systemHealth = "Good";
    
    if (avgBattery < 20) {
        systemHealth = "Bad";
    } else if (avgBattery < 50) {
        systemHealth = "Average";
    }
    
    // Update the system health text
    systemHealthElement.textContent = systemHealth;
    
    // Apply color class based on health status
    systemHealthElement.className = '';
    if (systemHealth === "Good") {
        systemHealthElement.classList.add('status-good');
    } else if (systemHealth === "Average") {
        systemHealthElement.classList.add('status-average');
    } else {
        systemHealthElement.classList.add('status-bad');
    }
    
    // Show a notification when system health changes to a better state
    if ((prevSystemHealth === "Bad" && systemHealth !== "Bad") || 
        (prevSystemHealth === "Average" && systemHealth === "Good")) {
        // Highlight the change with animation
        systemHealthElement.classList.add('status-improved');
        
        // Display a status message
        displayConnectionStatus(`System health improved to ${systemHealth}!`);
        
        // Remove the animation class after a delay
        setTimeout(() => {
            systemHealthElement.classList.remove('status-improved');
        }, 3000);
    }
    
    // Show a notification when system health worsens
    if ((prevSystemHealth === "Good" && systemHealth !== "Good") || 
        (prevSystemHealth === "Average" && systemHealth === "Bad")) {
        displayConnectionStatus(`System health deteriorated to ${systemHealth}!`, true);
    }
}

// Charge controls with improved error handling
function initChargeButtons() {
    document.addEventListener('click', async (e) => {
        if (!e.target.classList.contains('charge-button')) return;
        
        const button = e.target;
        const robotId = button.dataset.robotId;
        const charge = button.dataset.action === 'start';

        if (!robotId) {
            displayConnectionStatus('Invalid robot ID', true);
            return;
        }

        button.disabled = true;
        try {
            const response = await fetch(`/api/control/robot/${robotId}/charge`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ charge })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Charge command failed');
            }
            
            fetchRobotStatus(); // Immediate update
        } catch (error) {
            displayConnectionStatus(`Charge error: ${error.message}`, true);
        } finally {
            button.disabled = false;
        }
    });
}

// Task form handling with improved validation
function initTaskForm() {
    const form = document.getElementById('task-form');
    if (!form) {
        console.error('Task form not found');
        return;
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const robotId = document.getElementById('robot-select')?.value;
        const task = document.getElementById('task-select')?.value;

        if (!robotId || !task) {
            displayConnectionStatus('Please select both a robot and a task', true);
            return;
        }

        // Check if robot battery is 0
        if (robotData[robotId] && robotData[robotId].battery === 0) {
            // Create a more prominent error message
            showProminentError(`Robot ${robotId} not charged! Cannot assign task.`);
            return;
        }

        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) submitButton.disabled = true;

        try {
            const response = await fetch(`/api/control/robot/${robotId}/task`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ task })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Task assignment failed');
            }
            
            const result = await response.json();
            displayConnectionStatus(result.message || `Task "${task}" assigned to Robot ${robotId}`);
            form.reset();
            fetchRobotStatus();
        } catch (error) {
            displayConnectionStatus(`Task error: ${error.message}`, true);
        } finally {
            if (submitButton) submitButton.disabled = false;
        }
    });
}

// Function to display a prominent error message in the center of the screen
function showProminentError(message) {
    // Remove any existing error message
    const existingError = document.getElementById('prominent-error');
    if (existingError) {
        existingError.remove();
    }
    
    // Create new error message element
    const errorDiv = document.createElement('div');
    errorDiv.id = 'prominent-error';
    errorDiv.className = 'prominent-error';
    errorDiv.innerHTML = `
        <div class="error-content">
            <div class="error-icon">⚠️</div>
            <div class="error-message">${message}</div>
            <button class="error-close-btn" onclick="this.parentElement.parentElement.remove()">OK</button>
        </div>
    `;
    
    // Add to body
    document.body.appendChild(errorDiv);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (document.getElementById('prominent-error')) {
            document.getElementById('prominent-error').remove();
        }
    }, 5000);
}

// Initialize event listeners for task controls
function initTaskControls() {
    document.addEventListener('click', async (e) => {
        if (e.target.classList.contains('end-task-button')) {
            const robotId = e.target.dataset.robotId;
            const button = e.target;
            
            button.disabled = true;
            try {
                const response = await fetch(`/api/control/robot/${robotId}/end-task`, {
                    method: 'POST'
                });
                
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || 'Failed to end task');
                }
                
                const result = await response.json();
                displayConnectionStatus(result.message);
                fetchRobotStatus();
            } catch (error) {
                displayConnectionStatus(`Error ending task: ${error.message}`, true);
            } finally {
                button.disabled = false;
            }
        }
    });
}

// Page visibility handling with improved state management
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopPolling();
        pollingInterval = setInterval(fetchRobotStatus, 10000);
    } else {
        stopPolling();
        startPolling();
    }
});

// Initialize on load with error handling
window.addEventListener('DOMContentLoaded', () => {
    try {
        initDashboard();
    } catch (error) {
        console.error('Failed to initialize dashboard:', error);
        displayConnectionStatus('Failed to initialize dashboard. Please refresh the page.', true);
    }
});

// Show loading bar until data is fetched
function showLoadingBar() {
    const container = document.getElementById('robot-status-cards');
    if (!container) {
        console.error('Robot status cards container not found');
        return;
    }
    
    // Clear existing content
    container.innerHTML = '';
    
    // Create loading bar
    const loadingDiv = document.createElement('div');
    loadingDiv.id = 'loading-bar-container';
    loadingDiv.innerHTML = `
        <div class="loading-message">Loading robot data...</div>
        <div class="loading-bar-wrapper">
            <div class="loading-bar"></div>
        </div>
    `;
    
    container.appendChild(loadingDiv);
}

// Hide loading bar after data is fetched
function hideLoadingBar() {
    const loadingBar = document.getElementById('loading-bar-container');
    if (loadingBar) {
        loadingBar.remove();
    }
}

