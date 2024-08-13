#!/bin/bash

# Check if virtual environment exists
if [ ! -d "jannyBotEnv" ]; then
    echo "Virtual environment not found. Please run setup_jannybot.sh first."
    exit
fi

# Activate the virtual environment
source jannyBotEnv/Scripts/activate

# Run the bot
python jannybot.py

# Deactivate the virtual environment after the bot stops
deactivate
