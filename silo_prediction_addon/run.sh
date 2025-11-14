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
# Bashio returns each array element on a separate line, so we need to construct valid JSON
bashio::log.info "Starting Silo Prediction Add-on..."
bashio::log.info "Prediction days: $PREDICTION_DAYS"
bashio::log.info "Update interval: $UPDATE_INTERVAL seconds"

# Build JSON array from silos config
SILOS_JSON="["
SILO_COUNT=0
for entity_id in $(bashio::config 'silos|keys'); do
    if [ $SILO_COUNT -gt 0 ]; then
        SILOS_JSON="${SILOS_JSON},"
    fi

    ENTITY=$(bashio::config "silos[${entity_id}].entity_id")
    SENSOR_NAME=$(bashio::config "silos[${entity_id}].sensor_name")
    REFILL=$(bashio::config "silos[${entity_id}].refill_threshold")
    MAX_CAP=$(bashio::config "silos[${entity_id}].max_capacity")

    SILOS_JSON="${SILOS_JSON}{\"entity_id\":\"${ENTITY}\",\"sensor_name\":\"${SENSOR_NAME}\",\"refill_threshold\":${REFILL},\"max_capacity\":${MAX_CAP}}"
    SILO_COUNT=$((SILO_COUNT + 1))
done
SILOS_JSON="${SILOS_JSON}]"

export SILOS_CONFIG="$SILOS_JSON"
bashio::log.info "Configured silos: $SILO_COUNT"

# Start the Python service
exec python3 /app/silo_prediction.py
