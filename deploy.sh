#!/bin/bash
set -e

echo "======================================"
echo "    CUGB Sports Booking Deploy        "
echo "======================================"

# Check for python3
if ! command -v python3 &> /dev/null
then
    echo "Python3 could not be found. Please install Python 3.10+"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Stop existing process if running
if pgrep -f "webapp.py" > /dev/null; then
    echo "Stopping existing webapp..."
    pkill -f "webapp.py"
    sleep 2
fi

# Start app in background
echo "Starting webapp on port 8765..."
nohup python webapp.py > app.log 2>&1 &

echo "======================================"
echo "Deployment successful!"
echo "View logs: tail -f app.log"
echo "Stop app: pkill -f webapp.py"
echo "Access: http://<server_ip>:8765"
echo "======================================"
