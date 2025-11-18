# Silo Prediction - Quick Reference Card

## 🚀 Common Tasks

### Check Current Predictions
```bash
ha addons logs a6980454_silo_prediction | grep "📅.*Exp-only:"
```

### View Last Update
```bash
ha addons logs a6980454_silo_prediction | grep "Feldolgozás sikeres" | tail -2
```

### Check Exponential Constants
```bash
ha addons logs a6980454_silo_prediction | grep "📈.*Exp állandó:" | tail -2
```

### View Errors Only
```bash
ha addons logs a6980454_silo_prediction | grep -E "(ERROR|❌)"
```

### Restart Addon
```bash
ha addons restart a6980454_silo_prediction
```

## 📊 Current Status (as of 2025-11-18 23:13)

| Metric | CFM 3 Hall | CFM 1 Hall |
|--------|------------|------------|
| **Empty Date** | Nov 21, ~11:13 | Nov 21, ~07:13 |
| **Days Left** | 2.5 days | 2.3 days |
| **Exp Constant** | 0.005517 | 0.010304 |
| **Base Rate** | 3646.4 kg/day | 2574.2 kg/day |
| **Acceleration** | 20.12 kg/day² | 26.52 kg/day² |
| **Method** | Exp-only fallback | Exp-only fallback |
| **0-Day Status** | Detected (Nov 16) | Not detected |

## 📁 Key File Locations

| Purpose | Path |
|---------|------|
| **Main Code** | `/data/ha-silo-prediction/silo_prediction_addon/silo_prediction.py` |
| **Config** | `/data/ha-silo-prediction/silo_prediction_addon/config.yaml` |
| **Tech Data** | `/data/ha-silo-prediction/silo_prediction_addon/tech_feed_data.csv` |
| **Local Copy** | `/addons/silo_prediction/` |
| **Skill** | `/config/.claude/skills/silo-prediction/silo-prediction.md` |
| **Git Repo** | `/data/ha-silo-prediction/` |

## 🔧 Development Shortcuts

### Quick Code Edit Flow
```bash
# 1. Edit file
nano /data/ha-silo-prediction/silo_prediction_addon/silo_prediction.py

# 2. Update version
sed -i 's/version: "X.X.X"/version: "X.X.Y"/' /data/ha-silo-prediction/silo_prediction_addon/config.yaml

# 3. Commit & Push
cd /data/ha-silo-prediction
git add silo_prediction_addon/silo_prediction.py silo_prediction_addon/config.yaml
git commit -m "Description - vX.X.Y"
git push origin main

# 4. Copy locally (optional, for immediate testing)
cp silo_prediction_addon/silo_prediction.py /addons/silo_prediction/
cp silo_prediction_addon/config.yaml /addons/silo_prediction/

# 5. Update addon
ha supervisor reload
sleep 15
ha addons update a6980454_silo_prediction
```

### Emergency Rollback
```bash
cd /data/ha-silo-prediction
git log --oneline -5                    # Find good commit
git revert <commit-hash>                # Revert bad changes
# OR
git reset --hard <good-commit-hash>     # Hard reset (USE WITH CAUTION!)
git push origin main --force            # Force push (if needed)
```

## 🎯 Sensors

### CFM 3 Hall Silo
- `sensor.cfm_3_hall_silo_prediction` - Empty date/time
- `sensor.cfm_3_hall_silo_prediction_time_remaining` - Hours left
- `sensor.cfm_3_hall_silo_prediction_bird_count` - Bird count (or "unknown")
- `sensor.cfm_3_hall_silo_prediction_last_updated` - Last update time

### CFM 1 Hall Silo
- `sensor.cfm_1_hall_silo_prediction` - Empty date/time
- `sensor.cfm_1_hall_silo_prediction_time_remaining` - Hours left
- `sensor.cfm_1_hall_silo_prediction_bird_count` - Bird count (or "unknown")
- `sensor.cfm_1_hall_silo_prediction_last_updated` - Last update time

## 🔍 Log Patterns

### Success
```
✅ [Silo] TECH + EXP MÓDSZER használata
✅ [Silo] Feldolgozás sikeres
📈 [Silo] Exp állandó: 0.XXXXXX
🐣 [Silo] 0. NAP DETEKTÁLVA: YYYY-MM-DD
```

### Fallback (Normal)
```
⚠️ [Silo] EXP-ONLY FALLBACK MÓDSZER használata
⚠️ [Silo] Madár darabszám nem számolható, fallback...
⚠️ [Silo] 0. nap nem detektálható → Fallback módszer
```

### Errors (Need Attention!)
```
❌ [Silo] Hiba a feldolgozás során: ...
ERROR - ...
AttributeError: ...
```

## 🚨 Troubleshooting Cheatsheet

| Problem | Quick Fix |
|---------|-----------|
| **Addon not updating** | Bump version in config.yaml, wait 30s after reload |
| **Old code still running** | Check version: `ha addons info a6980454_silo_prediction` |
| **Sensors show "unknown"** | Normal if in fallback mode, check logs for errors |
| **No predictions** | Check "adatpont betöltve" in logs, ensure 45 days history |
| **Git push fails** | Check PAT token is set, try: `git remote -v` |

## 📞 Quick Diagnostics

```bash
# Full diagnostic output
ha addons info a6980454_silo_prediction && \
echo "---" && \
ha addons logs a6980454_silo_prediction | tail -50 && \
echo "---" && \
git -C /data/ha-silo-prediction log --oneline -3
```

## 🔗 Links

- **GitHub**: https://github.com/wfocsy/ha-silo-prediction
- **Skill**: [silo-prediction.md](./silo-prediction.md)
- **README**: [README.md](./README.md)
