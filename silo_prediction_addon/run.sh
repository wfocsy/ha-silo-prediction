#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
# ==============================================================================
# Home Assistant Add-on: Silo Prediction
# Runs the Silo Prediction service
# ==============================================================================

bashio::log.info "Starting Silo Prediction service..."

cd /app || exit 1

exec python3 prediction_service.py
