import argparse
import json
import sys

# ------------------ # 
from dependencies.utilities import  get_cluster_info
from dependencies.az_kube_helper import AzKubeCtlHelper
from dependencies.utilities import parse_alert_text, has_required_keys
from dependencies.aks_cluster_status import get_activity_logs, analyze_events


# --- ConfigMap Check Function ---
def check_configmap_auth_state(helper: AzKubeCtlHelper, configmap_name: str = "environment-auto"):
    """Checks the authentication_state in a specific ConfigMap to determine if the namespace is in a limited state."""
    print(f"\n--- Checking ConfigMap '{configmap_name}' for authentication_state ---")
    # cm_cmd = ["kubectl", "get", "configmap", configmap_name, "-n", helper.namespace, "-o", "json"]
    cm_stdout, cm_stderr = helper.get_configmap_data(configmap_name)

    if cm_stdout is not None:
        try:
            cm_data = json.loads(cm_stdout)
            # ConfigMap data is often stored as strings within the 'data' field
            config_data = cm_data.get('data', {})
            auth_state = config_data.get('authentication_state')

            if auth_state is not None:
                # print(f"Found authentication_state: '{auth_state}'")
                if auth_state.lower() == "limited":
                    print(f"ALERT: {helper.cluster_name}/{helper.namespace} Authentication state is LIMITED.")
                    # Potentially return a specific status code or boolean
                    return True # Indicate limited state found
                else:
                     print(f"Authentication state is {auth_state}.")
                     return False
            else:
                # print(f"Key 'authentication_state' not found in ConfigMap '{configmap_name}' data.")
                return False # Indicate key not found

        except json.JSONDecodeError:
            print("Error: Could not decode JSON output from kubectl get configmap.")
            print("Raw output:", cm_stdout)
            return False
        except Exception as e:
            print(f"An error occurred parsing ConfigMap data: {e}")
            return False
    else:
        if cm_stderr and "not found" in cm_stderr.lower():
             print(f"ConfigMap '{configmap_name}' not found in namespace '{helper.namespace}'.")
        else:
             print(f"Error getting ConfigMap '{configmap_name}': {cm_stderr.strip() if cm_stderr else 'Unknown'}")
        return False

# --- Main Execution Logic --- #
def execute_cluster_status_checks(helper: AzKubeCtlHelper):
    cluster_info = get_cluster_info(helper.cluster_name)
    resource_group = cluster_info.get("resource_group")
    # --- Run Base Status Checks --- 

    try:
        # --- Check Node Pool Status --- 
        print("\n--- Checking Node Pool Status --- ")
        # np_cmd = [helper.az_path, "aks", "nodepool", "list", "--cluster-name", helper.cluster_name, "--resource-group", helper.resource_group, "--output", "table"]
        np_stdout, np_stderr = helper.check_node_pool_status()
        if np_stdout is not None:
             print("Node Pool Status:")
             print(np_stdout)
        else:
             print(f"Error checking node pool status: {np_stderr.strip() if np_stderr else 'Unknown'}")

        # --- Check  Node Status/Versions (kubectl) --- 
        print("\n--- Checking Node Status & Versions --- ")
        # Note: Assumes kubectl is in PATH or _run_command handles finding it
        # node_cmd = ["kubectl", "get", "nodes", "-o", "wide"]
        node_stdout, node_stderr = helper.check_node_status()
        if node_stdout is not None:
             print("Node Status & Versions:")
             print(node_stdout)
        else:
             print(f"Error checking node status: {node_stderr.strip() if node_stderr else 'Unknown'}")
        
        print("\n--- Checking Maintenance Window --- ")
        mw = helper.get_maintenance_windows()
        print(f"Maintenance Window: {mw}")

        print("\n--- Analyze Last 1 day Activity Logs --- ")
        events = get_activity_logs(helper.az_path, resource_group, days=1)
        analyze_events(events, mw)
        print("\nBase status checks finished.") # Updated message
        
    except Exception as e:
        print(f"An error occurred during status checks: {e}")
        raise

def execute_base_status_checks(alert_details:dict):

    try:
        # Using cluster_name for target_name (output dir)
        helper = AzKubeCtlHelper(alert_details) 
        # --- Setup Context --- 
        setup_success = helper.setup_context()
        if not setup_success:
            print("\nContext setup failed. Cannot run checks.")
            sys.exit(1)

    except ValueError as e:
         print(f"Initialization Error: {e}")
         sys.exit(1)
    except Exception as e:
        print(f"Error initializing AzKubeCtlHelper: {e}")
        sys.exit(1)

    configmap_name = "environment-auto"
    print(f"Starting Base Status Check for Cluster: '{helper.cluster_name}', Namespace: '{helper.namespace}'...")
    check_configmap_auth_state(helper=helper)
    execute_cluster_status_checks(helper=helper)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diagnose AKS App Exceptions based on alert file.")
    parser.add_argument("--alert-text", required=True, help="Contents of the alert")
    args = parser.parse_args()
    alert_content = args.alert_text
    if not alert_content:
        print("Error: Alert text is required.")
        sys.exit(1)
    alert_details = parse_alert_text(alert_content)
    required_keys = ['cluster', 'namespace']
    if not has_required_keys(alert_details, required_keys):
        print(f"Error: Missing {required_keys} in alert_details.")
        sys.exit(1)
    execute_base_status_checks(alert_details)
