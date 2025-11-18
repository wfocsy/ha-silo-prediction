# Silo Prediction Project

Advanced silo empty prediction system for Home Assistant using exponential acceleration models and technological feed data.

## Project Status

**Version**: 6.5.7 (Deployed and Running)
**Status**: ✅ Production
**Last Updated**: 2025-11-18

## Quick Links

- **Skill**: [silo-prediction.md](./silo-prediction.md)
- **Repository**: https://github.com/wfocsy/ha-silo-prediction
- **Addon ID**: `a6980454_silo_prediction`

## Current Predictions

**CFM 3 Hall Silo**:
- Empty Date: 2025-11-21 10-12 óra között (~11:13)
- Time Remaining: 2.5 days
- Method: Exp-only fallback (bird count unavailable)

**CFM 1 Hall Silo**:
- Empty Date: 2025-11-21 06-08 óra között (~07:13)
- Time Remaining: 2.3 days
- Method: Exp-only fallback (no 0-day detected)

## Key Metrics

- **Exponential Constants**:
  - CFM 3: 0.005517 (base: 3646.4 kg/day, accel: 20.12 kg/day²)
  - CFM 1: 0.010304 (base: 2574.2 kg/day, accel: 26.52 kg/day²)
- **Historical Data**: 45 days
- **Sampling**: 6-hour for prediction, 5-min for refill detection
- **Tech Data Accuracy**: 87.1% correlation, 0.0% avg error

## Project Structure

```
/config/.claude/skills/silo-prediction/   # This directory
  ├── README.md                            # This file
  └── silo-prediction.md                   # Main skill

/data/ha-silo-prediction/                  # Git repository (VSCode addon storage)
  ├── silo_prediction_addon/               # Addon source code
  │   ├── silo_prediction.py              # Main prediction logic
  │   ├── config.yaml                      # Addon configuration
  │   ├── Dockerfile                       # Docker build file
  │   ├── tech_feed_data.csv              # Feed consumption data
  │   └── run.sh                           # Startup script
  └── .git/                                # Git repository

/addons/silo_prediction/                   # HA Supervisor local addon
  ├── silo_prediction.py                   # (copied from repo)
  ├── config.yaml                          # (copied from repo)
  └── ...

/data/                                      # Development files (VSCode storage)
  ├── INTEGRATION_COMPLETE.md              # Integration documentation
  ├── DEPLOYMENT_STATUS.md                 # Deployment status
  ├── exponential_prediction_prototype.py  # Prototype validation
  ├── analyze_tech_correlation.py          # Tech data validation
  └── compare_tech_vs_exp.py               # Method comparison
```

## Quick Commands

```bash
# View logs
ha addons logs a6980454_silo_prediction | tail -100

# Check status
ha addons info a6980454_silo_prediction

# Restart addon
ha addons restart a6980454_silo_prediction

# Update addon (after version bump)
ha supervisor reload && sleep 10 && ha addons update a6980454_silo_prediction
```

## Development Workflow

1. Edit code in `/data/ha-silo-prediction/silo_prediction_addon/`
2. Update version in `config.yaml`
3. Commit and push to GitHub
4. Copy to `/addons/silo_prediction/` (optional, for local testing)
5. Reload supervisor and update addon

## Created Sensors

- `sensor.cfm_3_hall_silo_prediction`
- `sensor.cfm_3_hall_silo_prediction_time_remaining`
- `sensor.cfm_3_hall_silo_prediction_bird_count`
- `sensor.cfm_3_hall_silo_prediction_last_updated`
- `sensor.cfm_1_hall_silo_prediction`
- `sensor.cfm_1_hall_silo_prediction_time_remaining`
- `sensor.cfm_1_hall_silo_prediction_bird_count`
- `sensor.cfm_1_hall_silo_prediction_last_updated`

## Algorithm Overview

### Dual-Mode Prediction

1. **Tech + Exp Mode** (when 0-day detected):
   - Estimates bird count from cycle start
   - Uses technological feed data (g/bird/day)
   - Applies exponential correction for acceleration
   - Most accurate when cycle data available

2. **Exp-Only Fallback** (when no 0-day):
   - Uses only historical consumption data
   - Calculates exponential acceleration
   - No bird count estimation needed
   - Robust fallback method

### Key Features

- **Exponential Acceleration**: Models increasing consumption as birds grow
- **5-Min Sampling**: Precise refill detection and completion
- **6-Hour Sampling**: Stable prediction curve (daily: 7:00, 13:00, 19:00, 1:00)
- **Refill Normalization**: Continuous curve despite multiple refills
- **Real-time Updates**: 24-hour cycle with 20-min post-refill updates

## Next Steps / Future Improvements

- [ ] Improve bird count estimation for better Tech+Exp accuracy
- [ ] Add prediction confidence intervals
- [ ] Historical prediction accuracy tracking
- [ ] Multi-cycle learning and adaptation
- [ ] Anomaly detection (unexpected consumption patterns)

## Support

For issues or questions:
1. Check logs first: `ha addons logs a6980454_silo_prediction`
2. Review [silo-prediction.md](./silo-prediction.md) skill
3. Check GitHub issues: https://github.com/wfocsy/ha-silo-prediction/issues
