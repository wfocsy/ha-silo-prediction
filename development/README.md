# Development Files

This directory contains all development, testing, and validation files used during the creation of the Silo Prediction addon.

## Directory Structure

### 📊 `prototypes/`
Early prototypes and experimental implementations:
- `exponential_prediction_prototype.py` - Initial exponential acceleration model prototype
- `silo_simulation.py` - Silo consumption simulation for testing

### ✅ `validation/`
Validation scripts that proved the accuracy of the prediction methods:
- `analyze_tech_correlation.py` - **Tech data validation (87.1% correlation, 0.0% error)**
- `compare_tech_vs_exp.py` - Comparison of Tech+Exp vs Exp-only methods
- `validate_prediction_accuracy.py` - Prediction accuracy validation
- `validation_and_prediction.py` - General validation framework
- `improved_validation.py` - Enhanced validation with additional metrics

### 🧪 `tests/`
Unit and integration tests used during development:
- `test_addon_fix.py` - Addon fix testing
- `test_fallback_mode.py` - Fallback mode validation
- `test_fix.py` - General fix testing
- `test_with_csv.py` - CSV data integration tests

### 🔍 `analysis/`
Analysis scripts for understanding consumption patterns:
- `analyze_csv_cycle.py` - Cycle analysis from CSV data
- `find_silence_period.py` - Silence period detection (for 0-day detection)
- `check_current_trend.py` - Current consumption trend analysis
- `check_sensor_details.py` - Sensor data inspection
- `check_statistics.py` - Statistical analysis
- `current_prediction_nov18.py` - Nov 18 prediction snapshot
- `live_prediction_now.py` - Real-time prediction testing

### 📄 `docs/`
Development documentation and analysis:
- `ADDON_PREDICTION_LOGIC_ANALYSIS.md` - Detailed prediction logic analysis
- `DEPLOYMENT_STATUS.md` - Deployment status and troubleshooting
- `INTEGRATION_COMPLETE.md` - Integration completion documentation
- `INTEGRATION_PLAN.md` - Original integration plan

### 📊 `data/`
Test and historical data files:
- `Blokkhistory3_4.csv` - Historical consumption data (2.5MB, Oct-Nov 2025)

## Key Validation Results

From `analyze_tech_correlation.py`:
- **Tech Data Correlation**: 87.1%
- **Average Error**: 0.0%
- **Correction Factor**: 1.021x
- **Conclusion**: Tech data is highly accurate and suitable for prediction

From `compare_tech_vs_exp.py`:
- **Tech+Exp Prediction**: Nov 20, 09:47 (1.5 days) - when 0-day detected
- **Exp-only Fallback**: Nov 21, 12:38 (2.7 days) - matches 3h trend perfectly
- **Conclusion**: Both methods work, dual-mode approach provides best coverage

## Usage Notes

These files are **archived** and not required for production operation. They are kept for:
1. **Reference**: Understanding how the algorithms were developed
2. **Validation**: Re-validating with new data if needed
3. **Future Development**: Basis for improvements and new features
4. **Documentation**: Historical record of development process

## Running Validation Scripts

Most scripts require historical data and Home Assistant API access:

```bash
# Example: Run tech correlation analysis
cd /data/ha-silo-prediction/development/validation
python3 analyze_tech_correlation.py

# Example: Compare prediction methods
python3 compare_tech_vs_exp.py
```

**Note**: Some scripts may need path adjustments to access addon code or CSV files.

## Production Code

The production addon code is in:
- `/data/ha-silo-prediction/silo_prediction_addon/`

These development files are **not** included in the Docker image.
