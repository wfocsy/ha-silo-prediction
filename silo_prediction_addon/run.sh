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
bashio::log.info "Starting Silo Prediction Add-on..."
bashio::log.info "Prediction days: $PREDICTION_DAYS"
bashio::log.info "Update interval: $UPDATE_INTERVAL seconds"

# Build JSON array from silos config using proper bashio array iteration
SILOS_JSON="["
SILO_COUNT=0

# Count silos first
NUM_SILOS=$(bashio::config 'silos | length')

# Iterate through array indices
for ((i=0; i<NUM_SILOS; i++)); do
    if [ $i -gt 0 ]; then
        SILOS_JSON="${SILOS_JSON},"
    fi

    ENTITY=$(bashio::config "silos[$i].entity_id")
    SENSOR_NAME=$(bashio::config "silos[$i].sensor_name")
    REFILL=$(bashio::config "silos[$i].refill_threshold")
    MAX_CAP=$(bashio::config "silos[$i].max_capacity")

    SILOS_JSON="${SILOS_JSON}{\"entity_id\":\"${ENTITY}\",\"sensor_name\":\"${SENSOR_NAME}\",\"refill_threshold\":${REFILL},\"max_capacity\":${MAX_CAP}}"
    SILO_COUNT=$((SILO_COUNT + 1))
done
SILOS_JSON="${SILOS_JSON}]"

export SILOS_CONFIG="$SILOS_JSON"
bashio::log.info "Configured silos: $SILO_COUNT"
bashio::log.info "DEBUG - SILOS_JSON: $SILOS_JSON"

# Start the Python service
exec python3 /app/silo_prediction.py
