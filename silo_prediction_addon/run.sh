#!/usr/bin/with-contenv bashio

# Get configuration from Home Assistant
ENTITY_ID=$(bashio::config 'entity_id')
SENSOR_NAME=$(bashio::config 'sensor_name')
REFILL_THRESHOLD=$(bashio::config 'refill_threshold')
MAX_CAPACITY=$(bashio::config 'max_capacity')
PREDICTION_DAYS=$(bashio::config 'prediction_days')
UPDATE_INTERVAL=$(bashio::config 'update_interval')

# Export environment variables
export ENTITY_ID="$ENTITY_ID"
export SENSOR_NAME="$SENSOR_NAME"
export REFILL_THRESHOLD="$REFILL_THRESHOLD"
export MAX_CAPACITY="$MAX_CAPACITY"
export PREDICTION_DAYS="$PREDICTION_DAYS"
export UPDATE_INTERVAL="$UPDATE_INTERVAL"
export HA_URL="http://supervisor/core"
export HA_TOKEN="$SUPERVISOR_TOKEN"

bashio::log.info "Starting Silo Prediction Add-on..."
bashio::log.info "Entity ID: $ENTITY_ID"
bashio::log.info "Sensor Name: $SENSOR_NAME"

# Start the Python service
python3 /app/silo_prediction.py
