# Silo Prediction Management Skill

You are helping manage the Silo Prediction addon for Home Assistant. This addon predicts when silos will be empty using exponential acceleration models and technological feed data.

## Addon Information

**Current Version**: 6.5.7
**Location**: `/data/ha-silo-prediction` (git repository) and `/addons/silo_prediction` (local copy)
**Addon ID**: `a6980454_silo_prediction`

## Key Features

1. **Dual-Mode Prediction**:
   - **Tech + Exp mode**: When 0-day (cycle start) is detected, uses bird count × tech feed data × exponential correction
   - **Exp-only fallback**: When no 0-day, uses only exponential acceleration from historical data

2. **Exponential Acceleration Model**:
   - Calculates exponential constant from historical consumption rates
   - Uses linear regression to find acceleration (slope/avg_rate)
   - Accounts for increasing feed consumption as birds grow

3. **5-Minute Sampling**: Only for refill detection and completion (10 min no increase)
4. **6-Hour Sampling**: For prediction curve (7:00, 13:00, 19:00, 1:00)
5. **Refill Normalization**: Subtracts all refills to create continuous consumption curve

## Created Sensors

For each configured silo, the addon creates 4 sensors:

1. `sensor.{silo_name}_prediction` - Predicted empty date/time (e.g., "2025-11-21 10-12 óra között")
2. `sensor.{silo_name}_prediction_time_remaining` - Time remaining (e.g., "2 nap 11 óra")
3. `sensor.{silo_name}_prediction_bird_count` - Estimated bird count (or "unknown" in fallback)
4. `sensor.{silo_name}_prediction_last_updated` - Last update timestamp

**Current silos**:
- CFM 3 Hall Silo: `sensor.cfm_3_hall_silo_prediction*`
- CFM 1 Hall Silo: `sensor.cfm_1_hall_silo_prediction*`

## Common Commands

### Check Addon Status
```bash
ha addons info a6980454_silo_prediction
```

### View Logs
```bash
ha addons logs a6980454_silo_prediction | tail -100
```

### Restart Addon
```bash
ha addons restart a6980454_silo_prediction
```

### Update Addon
```bash
ha supervisor reload
sleep 10
ha addons update a6980454_silo_prediction
```

### Rebuild Addon (after code changes)
```bash
ha addons rebuild a6980454_silo_prediction
```

## Development Workflow

### Making Code Changes

1. **Edit the main file**:
   - Repository: `/data/ha-silo-prediction/silo_prediction_addon/silo_prediction.py`
   - Local copy: `/addons/silo_prediction/silo_prediction.py`

2. **Update version** in both:
   - `/data/ha-silo-prediction/silo_prediction_addon/config.yaml`
   - `/addons/silo_prediction/config.yaml`

3. **Commit and push**:
```bash
cd /data/ha-silo-prediction
git add silo_prediction_addon/silo_prediction.py silo_prediction_addon/config.yaml
git commit -m "Description of changes - vX.X.X"
git push origin main
```

4. **Copy to local addon** (for immediate testing):
```bash
cp /data/ha-silo-prediction/silo_prediction_addon/silo_prediction.py /addons/silo_prediction/
cp /data/ha-silo-prediction/silo_prediction_addon/config.yaml /addons/silo_prediction/
```

5. **Reload and update**:
```bash
ha supervisor reload
sleep 15
ha addons update a6980454_silo_prediction
```

**Note**: Due to Docker build cache, sometimes you need to bump the version number in config.yaml for the update to be recognized.

## Key Log Patterns to Look For

### Success Indicators
```
✅ [Silo Name] TECH + EXP MÓDSZER használata
⚠️ [Silo Name] EXP-ONLY FALLBACK MÓDSZER használata
📈 [Silo Name] Exp állandó: X.XXXXXX, alap ráta: XXXX.X kg/nap, gyorsulás: XX.XX kg/nap²
🐣 [Silo Name] 0. NAP DETEKTÁLVA: YYYY-MM-DD
✅ [Silo Name] Szenzor frissítve: sensor.xxx = value
✅ [Silo Name] Feldolgozás sikeres
```

### Warning Indicators
```
⚠️ [Silo Name] Madár darabszám nem számolható, fallback...
⚠️ [Silo Name] 0. nap nem detektálható → Fallback módszer
```

### Error Indicators
```
❌ [Silo Name] Hiba a feldolgozás során: ...
ERROR - ...
```

## Configuration

Config file: `/data/ha-silo-prediction/silo_prediction_addon/config.yaml`

Key settings:
- `prediction_days`: Historical data window (45 days recommended)
- `update_interval`: Update frequency in seconds (86400 = 24 hours)
- `refill_threshold`: Minimum weight increase to detect refill (1000 kg)
- `max_capacity`: Maximum silo capacity (20000 kg)

## Troubleshooting

### Addon not updating after code change
**Issue**: Docker build cache prevents new code from being copied
**Solution**:
1. Bump version number in config.yaml
2. Wait 15-30 seconds after `ha supervisor reload`
3. Try `ha addons rebuild` if update still not available

### AttributeError or undefined variable
**Issue**: Code has a bug
**Solution**: Check logs, fix the error in silo_prediction.py, commit, push, update version, reload

### Prediction showing "unknown" or errors
**Issue**: Not enough historical data or refills not detected properly
**Solution**:
- Ensure `purge_keep_days: 45` in Home Assistant recorder config
- Check if weight sensor data is available
- Look for "Adatok lekérése" and "adatpont betöltve" in logs

### Sensors not appearing in Home Assistant
**Issue**: Sensor creation failed
**Solution**: Check logs for "Szenzor frissítve" messages, restart addon

## Technical Architecture

### Key Methods

1. **`calculate_exp_constant()`** (line ~884-899):
   - Calculates exponential constant from 24-hour windows
   - Returns: (exp_constant, base_rate, acceleration)

2. **`predict_with_tech_and_exp()`** (line ~901-961):
   - Primary prediction using tech data + exponential correction
   - Requires: bird_count, cycle_start_date, base_rate, acceleration

3. **`predict_with_exp_only()`** (line ~963-1007):
   - Fallback prediction using only exponential acceleration
   - No bird count or tech data needed

4. **`resample_5min()`** (line ~747-813):
   - 5-minute sampling for refill detection only
   - NOT used for prediction curve

5. **`check_active_refill()`** (line ~853-882):
   - Detects active refills and completion
   - Returns "Feltöltés alatt" status during refill

### Process Flow

1. Fetch 45 days of historical data
2. Check for active refill (5-min sampling)
3. Sample data at 6-hour intervals for prediction
4. Calculate exponential constant
5. Detect 0-day (cycle start)
6. **Choose prediction mode**:
   - If 0-day found → Tech + Exp (or Exp-only if bird count fails)
   - If no 0-day → Exp-only fallback
7. Update Home Assistant sensors

## Git Repository

**URL**: https://github.com/wfocsy/ha-silo-prediction
**Branch**: main
**Authentication**: GitHub PAT configured

## Related Files

### Production Code
- **Main addon code**: `/data/ha-silo-prediction/silo_prediction_addon/silo_prediction.py` (79KB)
- **Tech feed data**: `/data/ha-silo-prediction/silo_prediction_addon/tech_feed_data.csv`
- **Config**: `/data/ha-silo-prediction/silo_prediction_addon/config.yaml`
- **Dockerfile**: `/data/ha-silo-prediction/silo_prediction_addon/Dockerfile`

### Development Files (Archived)
All development files are now organized in `/data/ha-silo-prediction/development/`:
- **Prototypes**: `development/prototypes/exponential_prediction_prototype.py`
- **Validation**: `development/validation/analyze_tech_correlation.py`, `compare_tech_vs_exp.py`
- **Tests**: `development/tests/test_*.py`
- **Analysis**: `development/analysis/check_*.py`, `find_silence_period.py`
- **Documentation**: `development/docs/*.md`
- **Test Data**: `development/data/Blokkhistory3_4.csv` (2.5MB)

See `development/README.md` for full details.

## When User Asks About Silo Prediction

Use this skill to:
1. Check current predictions and sensor values
2. View logs and diagnose issues
3. Update code and deploy changes
4. Explain how the prediction algorithms work
5. Troubleshoot problems
6. Show prediction accuracy and statistics

Always check the logs first to understand current state before making recommendations.
