#!/bin/bash

LOG_FILE="nohup.out"
PROGRAM_COMMAND="python3 cat.py"

while true; do
    # Check if program is running
    if ! pgrep -f "cat.py" > /dev/null; then
        echo "$(date): Program is not running. Starting it..."
        # Clear the log file before starting the program
        > $LOG_FILE
        nohup $PROGRAM_COMMAND &
    fi

    # Check logs for camera error
    if tail -n 50 $LOG_FILE | grep -q "Camera frontend has timed out!"; then
        echo "$(date): Camera error detected. Restarting program..."
        pkill -f "cat.py"  # Stop the running program
        # Clear the log file before restarting the program
        > $LOG_FILE
        nohup $PROGRAM_COMMAND &  # Restart the program
    fi

    sleep 10  # Check every 10 seconds
done
