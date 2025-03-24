# simulation/Dockerfile

FROM python:3.9-slim

WORKDIR /app

# Copy dependency definitions and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the source code
COPY . .

# Set the entrypoint to run simulation or consumer based on environment variable
# For example, if MODE=simulation, run simulation.py; if MODE=consumer, run consumer.py
CMD ["sh", "-c", "if [ \"$MODE\" = \"simulation\" ]; then python simulation.py; else python consumer.py; fi"]
