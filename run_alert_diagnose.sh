#!/bin/bash

# Streamlit Runner Script
# This script runs a Streamlit application

# Exit immediately if a command exits with a non-zero status
set -e

# Define the path to the main UI file
STREAMLIT_APP_PATH="app/main_ui.py"

# Check if the app file exists
if [ ! -f "$STREAMLIT_APP_PATH" ]; then
    echo "Error: Streamlit app file not found at $STREAMLIT_APP_PATH"
    exit 1
fi

# Run the Streamlit application
echo "Starting Streamlit application..."
python3 -m streamlit run "$STREAMLIT_APP_PATH"