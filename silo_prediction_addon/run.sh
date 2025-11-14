#!/usr/bin/with-contenv bashio

# Get global configuration
PREDICTION_DAYS=$(bashio::config 'prediction_days')
UPDATE_INTERVAL=$(bashio::config 'update_interval')

# Export global environment variables
export PREDICTION_DAYS="$PREDICTION_DAYS"
export UPDATE_INTERVAL="$UPDATE_INTERVAL"
export HA_URL="http://supervisor/core"

# The SUPERVISOR_TOKEN is automatically available in the environment
if [ -n "$SUPERVISOR_TOKEN" ]; then
    export HA_TOKEN="$SUPERVISOR_TOKEN"
    bashio::log.info "Token available (${#SUPERVISOR_TOKEN} chars)"
else
    bashio::log.error "SUPERVISOR_TOKEN not found!"
fi

# Export silos configuration as JSON
# This uses bashio to read the entire silos array and convert to JSON
SILOS_JSON=$(bashio::config 'silos')
export SILOS_CONFIG="$SILOS_JSON"

bashio::log.info "Starting Silo Prediction Add-on..."
bashio::log.info "Prediction days: $PREDICTION_DAYS"
bashio::log.info "Update interval: $UPDATE_INTERVAL seconds"

# Count silos
SILO_COUNT=$(echo "$SILOS_JSON" | jq '. | length')
bashio::log.info "Configured silos: $SILO_COUNT"

# Start the Python service
exec python3 /app/silo_prediction.py
