import json
from datetime import datetime, timedelta, timezone

from dependencies.utilities import run_command


def get_activity_logs(az_path,resource_group, days=7):
    print("Fetching AKS Activity Logs...")
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    
    cmd = (
        f"{az_path} monitor activity-log list "
        f"--resource-group {resource_group} "
        f"--start-time {start_time.isoformat()} "
        f"--end-time {end_time.isoformat()} "
        f"--query \"[?operationName.value=='Microsoft.ContainerService/managedClusters/agentPools/write']\""
    )
    output, error = run_command(cmd)
    if output:
        print(f"Activity logs fetched successfully: {output}")
        return json.loads(output)
    else:
        print(f"Error fetching activity logs: {error}")
        return []

def is_within_maintenance(event_time, windows):
    # Convert event_time to UTC and check if it fits any window
    dt = datetime.strptime(event_time, "%Y-%m-%dT%H:%M:%S.%fZ")
    event_day = dt.strftime("%A")
    event_time_only = dt.time()

    for w in windows:
        if w["day"] != event_day:
            continue
        if w["start"] < w["end"]:
            if w["start"] <= event_time_only <= w["end"]:
                return True
        else:
            # Window spans midnight
            if event_time_only >= w["start"] or event_time_only <= w["end"]:
                return True
    return False

def analyze_events(events, maintenance_windows):
    print("Analyzing 'Create or Update Agent Pool' events...\n")
    if not events:
        print("No recent 'Create or Update Agent Pool' operations found.")
        return

    for event in events:
        print(f"Find event: {event}")
        time_str = event.get("eventTimestamp")
        status = event.get("status", {}).get("value", "Unknown")
        caller = event.get("caller", "Unknown")
        sub_status = event.get("subStatus", {}).get("value", "")
        maintenance = is_within_maintenance(time_str, maintenance_windows)
        
        reason = "Automated maintenance window" if maintenance else (
            "Possibly manual or out-of-window automation"
        )

        print(f"Time: {time_str}")
        print(f"Status: {status} ({sub_status})")
        print(f"Caller: {caller}")
        print(f"Likely Cause: {reason}")
        print("\n")
