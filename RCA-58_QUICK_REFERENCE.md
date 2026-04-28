# RCA-58: Quick Reference Guide

## 🎯 Quick Commands

### Health Check Script
```bash
# Run full health check
python3 scripts/health_check.py

# Check exit code
echo $?  # 0 = healthy, 1 = unhealthy
```

### API Endpoint
```bash
# Get detailed health
curl http://localhost:8000/api/system-health-detailed | jq .

# Check overall status
curl http://localhost:8000/api/system-health-detailed | jq '.overall_status'

# Get summary
curl http://localhost:8000/api/system-health-detailed | jq '.summary'
```

### Scheduler Logs
```bash
# View real-time logs
tail -f /app/logs/scheduler.log

# Check health check job
grep "health_check_detailed" /app/logs/scheduler.log

# View successful jobs
grep "✅ Job" /app/logs/scheduler.log

# View failed jobs
grep "❌ Job" /app/logs/scheduler.log
```

---

## 📊 Health Checks

| Check | What it validates | Healthy if |
|-------|------------------|------------|
| **Data Quality** | Mock data, incident count | mock_count=0 AND incidents>0 |
| **GitHub Sync** | Last sync time | sync_age < 2x interval |
| **Scheduler** | Job execution | No recent errors |
| **Agents** | Activity events | Activity in last 2h |

---

## ✅ Acceptance Criteria Status

- [x] `scripts/health_check.py` created and working
- [x] Enhanced logging in scheduler
- [x] `/system-health-detailed` endpoint added
- [x] Hourly health check job in scheduler
- [x] All checks write to logs (not Slack)
- [x] Exit codes: 0 for healthy, 1 for unhealthy

---

## 🧪 Testing

```bash
# Run validation script
./test_monitoring.sh

# Expected output: ✅ ALL VALIDATION CHECKS PASSED
```

---

## 📁 Key Files

| File | Purpose | Lines |
|------|---------|-------|
| `scripts/health_check.py` | Standalone health validator | 482 |
| `scheduler/runner.py` | Enhanced job logging + hourly check | Modified |
| `dashboard/api/main.py` | `/system-health-detailed` endpoint | Modified |
| `test_monitoring.sh` | Validation script | 190 |

---

## 🔔 Alert Thresholds

| Component | Warning Threshold | Critical Threshold |
|-----------|------------------|-------------------|
| Mock Data | > 0 incidents | N/A |
| GitHub Sync | > 1x interval | > 2x interval |
| Agent Activity | > 2 hours | > 4 hours |
| Scheduler Errors | > 0 errors | > 5 errors |

---

## 🚀 Deployment Checklist

- [ ] Code deployed to production
- [ ] Docker containers restarted
- [ ] Health check script tested
- [ ] API endpoint verified
- [ ] Scheduler logs monitored
- [ ] First hourly check completed

---

## 📈 Success Metrics

**Before RCA-58:**
- ❌ No automated health validation
- ❌ Basic job logging only
- ❌ Manual health checks required
- ❌ No data quality validation

**After RCA-58:**
- ✅ Automated hourly health checks
- ✅ Detailed job execution logs with tracebacks
- ✅ Comprehensive health API
- ✅ Mock data detection
- ✅ Scheduler job monitoring
- ✅ Agent activity tracking
- ✅ GitHub sync validation
