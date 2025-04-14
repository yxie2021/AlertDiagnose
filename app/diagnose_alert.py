import os
import sys
from datetime import datetime
import argparse

from dependencies.az_kube_helper import AzKubeCtlHelper
from dependencies.utilities import parse_alert_text, has_required_keys

# --- Helper Functions --- #
def diagnose_alert(alert_content):
    helper = None
    alert_details = parse_alert_text(alert_content)
    if not alert_details:
        print("Exiting: Could not parse alert details.")
        sys.exit(1)
    try:
        helper = AzKubeCtlHelper(alert_details,
                               log_lines=200,
                               base_output_dir=os.path.join(os.getcwd(), "output"))
    except Exception as e:
        print(f"Error initializing AzKubeCtlHelper: {e}")
        sys.exit(1)

    # Setup Context
    print("\nAttempting context setup via helper...")
    setup_success = helper.setup_context()
    if not setup_success:
        print("\nContext setup failed. Cannot run diagnose.")
        sys.exit(1)

    # Run Diagnostics
    print("\nContext setup successful. Running diagnostics via helper...")
    
    if helper.pod_name or helper.app_name:
        helper.diagnose_pods()
    elif helper.job_name:
        helper.diagnose_job()

    sys.exit(1)


# --- Main Execution Logic --- #
def main():
    # --- Argument Parsing --- 
    parser = argparse.ArgumentParser(description="Diagnose AKS App Exceptions based on alert file.")
    parser.add_argument("--alert-text", required=True, help="Contents of the alert")
    args = parser.parse_args()
    alert_content = args.alert_text
    print(f"Starting diagnosis using AzKubeCtlHelper for alert")
    diagnose_alert(alert_content)
    
if __name__ == "__main__":
    main() 