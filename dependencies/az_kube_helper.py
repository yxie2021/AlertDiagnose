import os
import json
import subprocess
from datetime import datetime, timedelta
from dateutil import parser

from dependencies.utilities import setup_az_context, find_executable_path, run_command,get_cluster_info, has_required_keys

class AzKubeCtlHelper:
    """Helper class to manage Azure context and run kubectl diagnostics for Apps or Jobs."""

    def __init__(self, alert_details: dict, log_lines =200,  base_output_dir="output"):
        """Initialize with target cluster info and configuration paths."""
        required_keys = ['cluster']
        if not has_required_keys(alert_details, required_keys):
            raise ValueError(f"Missing {required_keys} in alert_details.")
            
        self.cluster_name = alert_details['cluster']
        self.namespace = alert_details.get('namespace', None)
        self.subscription_id = alert_details.get('subscription_id', None)
        self.resource_group = alert_details.get('resource_group', None)
        # Store both, but prioritize app_name for output dir if both given
        self.app_name = alert_details.get('app', None)
        self.job_name = alert_details['job_name'] if 'job_name' in alert_details else alert_details.get('job', None)
        self.pod_name = alert_details.get('pod', None)
        self.container_name = alert_details.get('container', None)
        self.service_name = alert_details.get('service', None)
        self.deployment_name = alert_details.get('deployment', None)

        self.cluster_info=get_cluster_info(self.cluster_name)
        
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        self.base_output_dir = os.path.join(base_output_dir, f"alert_{timestamp}")
        self.output_info_dir = os.path.join(self.base_output_dir, "info")
        self.output_log_dir = os.path.join(self.base_output_dir, "log")
        self.prev_log_dir = os.path.join(self.output_log_dir, "previous") # Define previous log dir path, in case of restarts
        self.log_lines = log_lines      #how many lines of logs to retrieve and save to output
        self.ensure_output_dirs()
        print(f"Output will be saved under: {self.base_output_dir}")

        # Internal state
        self.az_path = find_executable_path("az.cmd")
        self.credential = None # To store the SDK credential object
        
        self.is_context_set = False
        
        print(f"AKubeCtlHelper initialized for target cluster '{self.cluster_name}', namespace '{self.namespace}'.")

    def setup_context(self):
        """Performs login, finds cluster info, and sets az/kubectl context."""
        self.is_context_set=setup_az_context(self.subscription_id, self.resource_group, self.cluster_name,self.az_path)
        return self.is_context_set

    def ensure_output_dirs(self):
        """Ensures all output directories exist."""
        os.makedirs(self.output_info_dir, exist_ok=True)
        os.makedirs(self.output_log_dir, exist_ok=True)
        os.makedirs(self.prev_log_dir, exist_ok=True)
            
    # --- Internal Kubectl Methods ---
    
    # Consolidated function to get pods based on name prefix using self.target_name
    def _get_target_pods_by_prefix(self, target_name):
        # target_name is the name of the app or job
        if not self.namespace:
            print("Error: namespace not required for pod retrieval")
            return None
        
        """Gets all pods in the namespace and filters by self.target_name prefix."""
        if not target_name:
            print("Error: target_name (app_name or job_name) not set for this helper instance.")
            return None
        
        print(f"\nGetting all pods in namespace '{self.namespace}' to find prefix '{target_name}'...")
        #stdout, stderr = self._run_command(["kubectl", "get", "pods", "-n", self.namespace, "-o", "json"])
        stdout, stderr = run_command(["kubectl", "get", "pods", "-n", self.namespace, "-o", "json"])

        if stdout is None:
            if stderr and "command not found" not in stderr.lower():
                 print(f"Failed to get pods information from kubectl. Error: {stderr.strip() if stderr else 'Unknown'}")
            return None 

        try:
            pods_json = json.loads(stdout)
            all_pods_in_namespace = pods_json.get('items', [])
            if not all_pods_in_namespace:
                print(f"No pods found in namespace '{self.namespace}'.")
                return []
                
            matching_pods = []
            for pod in all_pods_in_namespace:
                pod_name = pod.get('metadata', {}).get('name', '')
                # Filter using the consolidated target_name
                if pod_name.startswith(target_name):
                    matching_pods.append(pod)
                    
            if not matching_pods:
                print(f"No pods found with name starting with '{target_name}' in namespace '{self.namespace}'.")
                return []
                
            print(f"Found {len(matching_pods)} pod(s) matching prefix '{target_name}'.")
            return matching_pods
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON output from kubectl get pods. {stderr}, {stdout}")
            return None 
        except Exception as e:
            print(f"An unexpected error occurred during pod filtering: {e}")
            return None

    def _describe_pod(self, pod_name):
        """Describes a pod, saves output, and returns success status and restart counts per container."""
        output_filename = os.path.join(self.output_info_dir, f"{pod_name}_info.log")
        print(f"Describing pod {pod_name} and getting status via JSON...")
        
        # --- Get Human-Readable Describe Output and Save --- 
        desc_success = False
        desc_stdout, desc_stderr = run_command(["kubectl", "describe", "pod", pod_name, "-n", self.namespace])
        if desc_stdout is not None:
            try:
                with open(output_filename, 'w', encoding='utf-8') as f:
                    f.write(desc_stdout)
                print(f"Full describe output saved to: {output_filename}")
                desc_success = True 
            except Exception as e:
                print(f"Error saving describe output to {output_filename}: {e}")
        else:
            print(f"Could not describe pod {pod_name}. Error: {desc_stderr}")
            
        # --- Get JSON Output for Parsing Restart Counts --- 
        restart_counts = {} # Dictionary: container_name -> restart_count
        json_stdout, json_stderr = run_command(["kubectl", "get", "pod", pod_name, "-n", self.namespace, "-o", "json"])
        
        if json_stdout is not None:
            try:
                pod_data = json.loads(json_stdout)
                container_statuses = pod_data.get('status', {}).get('containerStatuses', [])
                init_container_statuses = pod_data.get('status', {}).get('initContainerStatuses', [])
                
                all_statuses = container_statuses + init_container_statuses
                
                if not all_statuses:
                     print("Warning: No container statuses found in pod JSON.")
                else:
                    for status in all_statuses:
                        c_name = status.get('name')
                        r_count = status.get('restartCount', 0)
                        if c_name:
                            restart_counts[c_name] = r_count
  
            except json.JSONDecodeError:
                print(f"Error: Could not decode JSON output from kubectl get pod. {json_stderr}, {json_stdout}")
            except Exception as parse_error:
                 print(f"Warning: Error parsing pod JSON for restart counts - {parse_error}")
        else:
             print(f"Could not get pod JSON for restart counts. Error: {json_stderr}")

        # Return overall success (based on describe saving) and the restart dict
        return desc_success, restart_counts 
            
    def _get_pod_logs(self, pod_name, pod_spec, restart_counts_dict):
        """Gets current and previous logs based on restart counts dict."""
        print(f"Fetching logs for pod {pod_name} (Current tail={self.log_lines}, checking previous based on restartcounts)... ")
        containers = pod_spec.get('containers', [])
        init_containers = pod_spec.get('initContainers', [])
        if not containers and not init_containers:
            print("No containers found in pod spec.")
            return

        all_containers = containers + init_containers
        
        # Previous log dir setup (move creation maybe to diagnose methods?)
        previous_log_dir = os.path.join(self.output_log_dir, "previous")
        # Ensure it exists *before* the loop if any restarts might occur
        if any(count > 0 for count in restart_counts_dict.values()):
             try:
                 os.makedirs(previous_log_dir, exist_ok=True)
             except Exception as e:
                 print(f"Warning: Could not create previous log directory '{previous_log_dir}': {e}")
                 restart_counts_dict = {} # Clear dict to prevent save attempts

        for container in all_containers:
            container_name = container.get('name')
            # Get the specific restart count for this container
            restart_count = restart_counts_dict.get(container_name, 0)
            print(f"-- Processing container: {container_name} (Restarts: {restart_count}) --")

            # --- Get Current Logs --- 
            log_cmd = ["kubectl", "logs", pod_name, "-n", self.namespace, "-c", container_name, f"--tail={self.log_lines}"]
            log_stdout, log_stderr = run_command(log_cmd)
            output_filename = os.path.join(self.output_log_dir, f"{pod_name}_log_{container_name}.log")

            if log_stdout is not None:
                log_content_stripped = log_stdout.strip()
                print(f"--- Current Logs (Container: {container_name}, Last {self.log_lines} lines) ---")
                # print(log_content_stripped if log_content_stripped else "(No recent log output)")
                if log_content_stripped:
                    try:
                        with open(output_filename, 'w', encoding='utf-8') as f:
                            f.write(log_stdout)
                        print(f"Current logs for container '{container_name}' saved to: {output_filename}")
                    except Exception as e:
                        print(f"Error saving current logs for container '{container_name}' to {output_filename}: {e}")
                else:
                    print(f"Skipping save for empty current logs from container '{container_name}'.")
            elif log_stderr:
                print(f"Could not retrieve current logs for pod {pod_name}, container {container_name}. Error: {log_stderr.strip() if log_stderr else 'Unknown'}")
            else:
                print(f"Could not retrieve current logs for pod {pod_name}, container {container_name}. No stdout or stderr.")

            # --- Get Previous Logs (check specific container restart_count) --- 
            if restart_count > 0:
                print(f"-- Checking previous logs for container: {container_name} (Restart Count: {restart_count}) --")
                prev_log_cmd = ["kubectl", "logs", pod_name, "-n", self.namespace, "-c", container_name, "--previous"] # No tail needed for previous
                prev_log_stdout, prev_log_stderr = run_command(prev_log_cmd)
                prev_output_filename = os.path.join(previous_log_dir, f"{pod_name}_log_{container_name}_previous.log")
                
                if prev_log_stdout is not None:
                    prev_log_content_stripped = prev_log_stdout.strip()
                    print(f"--- Previous Logs (Container: {container_name}) ---")
                    # print(prev_log_content_stripped if prev_log_content_stripped else "(No previous log output)")
                    if prev_log_content_stripped:
                        try:
                            with open(prev_output_filename, 'w', encoding='utf-8') as f:
                                f.write(prev_log_stdout)
                            print(f"Previous logs for container '{container_name}' saved to: {prev_output_filename}")
                        except Exception as e:
                            print(f"Error saving previous logs for container '{container_name}' to {prev_output_filename}: {e}")
                    else:
                        print(f"Skipping save for empty previous logs from container '{container_name}'.")
                elif prev_log_stderr:
                    # Common error if no previous container exists
                    if "previous terminated container" in prev_log_stderr.lower():
                         print(f"No previous logs found for container '{container_name}'.")
                    else:
                         print(f"Could not retrieve previous logs for pod {pod_name}, container {container_name}. Error: {prev_log_stderr.strip() if prev_log_stderr else 'Unknown'}")
                else:
                    print(f"Could not retrieve previous logs for pod {pod_name}, container {container_name}. No stdout or stderr (or no previous container)." )

    # --- Public Diagnostic Method ---
    def diagnose_pods(self):
        """Runs the full diagnostic process: find pods, describe, get logs."""
        if not self.is_context_set:
            print("Error: Context not set up. Please call setup_context() first.")
            return

        print("\n--- Starting Pod Investigation ---")

        if self.pod_name:
            target_name = self.pod_name
        else:
            # app or job could associated with a pod
            target_name = self.app_name or self.job_name
        if not target_name:
            print("Error: target_name (app or job) not set for this helper instance.")
            return
            
        pods = self._get_target_pods_by_prefix(target_name)

        if pods is None:
            print(f"Pod investigation failed due to error retrieving pod information for {target_name}.")
            return

        for pod_data in pods:
            pod_name = pod_data.get('metadata', {}).get('name')
            pod_status = pod_data.get('status', {}).get('phase')
            pod_spec = pod_data.get('spec', {})
            print(f"\n--- Details for Pod: {pod_name} (Status: {pod_status}) ---")
            # Capture restart counts dict from _describe_pod
            desc_success, restart_counts = self._describe_pod(pod_name)
            # Pass restart_counts dict to _get_pod_logs
            self._get_pod_logs(pod_name, pod_spec, restart_counts)

        print("\n--- End of Pod Investigation ---")

    # --- Job Specific Diagnostics (NEW) --- #
    def _describe_job(self):
        """Describes the job and saves the output."""
        if not self.job_name:
             print("Error: job_name not set for this helper instance.")
             return False
        output_filename = os.path.join(self.output_info_dir, f"{self.job_name}_info.log")
        print(f" Describing job '{self.job_name}'...")
        # Use self.namespace which was set in __init__
        cmd = ["kubectl", "describe", "job", self.job_name, "-n", self.namespace]
        desc_stdout, desc_stderr = run_command(cmd)
        
        if desc_stdout is not None:
            try:
                with open(output_filename, 'w', encoding='utf-8') as f:
                    f.write(desc_stdout)
                print(f"Full job describe output saved to: {output_filename}")
                # Optional: Print key status/events to console
                print("--- Job Description (Status/Events Snippet) ---")
                lines = desc_stdout.splitlines()
                event_lines_found = False
                for i, line in enumerate(lines):
                    l_strip = line.strip()
                    if l_strip.startswith("Status:") or l_strip.startswith("Conditions:") or l_strip.startswith("Events:"):
                         # Print section header and maybe next few lines
                         print("\n" + line)
                         for j in range(1, min(4, len(lines) - 1 - i)):
                              print(lines[i+j])
                         if l_strip.startswith("Events:"): event_lines_found = True
                if not event_lines_found: print("\n(No Events section found)")
                print("--------------------------------------------")
                return True
            except Exception as e:
                print(f"Error saving job describe output to {output_filename}: {e}")
                return False
        else:
            print(f"Could not describe job {self.job_name}. Error: {desc_stderr}")
            return False
            
    def diagnose_job(self):
        """Runs the full diagnostic process for jobs."""
        if not self.job_name:
            print("Error: diagnose_job called, but no job_name was provided during initialization.")
            return
        if not self.is_context_set:
            print("Error: Context not set up. Please call setup_context() first.")
            return

        print(f"\n--- Starting Job Investigation for '{self.job_name}' --- ")

        self._describe_job()

        self.diagnose_pods()

        print("\n--- End of Job Investigation ---")
        print("Job diagnosis complete.")

    def get_configmap_data(self, configmap_name: str):
        """
        Retrieves the data from a specified ConfigMap in a given namespace.
        """
        cm_cmd = ["kubectl", "get", "configmap", configmap_name, "-n", self.namespace, "-o", "json"]
        return run_command(cm_cmd)

    def query_maintenance_windows(self):
        """Run Azure CLI command to get maintenance configuration"""
        cmd = [
            self.az_path, "aks", "maintenanceconfiguration", "list",
            "--resource-group", self.cluster_info.get("resource_group"),
            "--cluster-name", self.cluster_name,
            "-o", "json"
        ]
        
        try:
            output, error = run_command(cmd)
            return json.loads(output)
        except subprocess.CalledProcessError as e:
            print(f"Error running Azure CLI command: {e}")
            print(f"Error output: {e.stderr}")
            return None
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON: {e}")
            return None

    def check_node_pool_status(self):
        np_cmd = [self.az_path, "aks", "nodepool", "list", "--cluster-name", self.cluster_name, "--resource-group", self.cluster_info.get("resource_group"), "--output", "table"]
        np_stdout, np_stderr = run_command(np_cmd)
        return np_stdout, np_stderr

    def check_node_status(self):
        node_cmd = ["kubectl", "get", "nodes", "-o", "wide"]
        node_stdout, node_stderr = run_command(node_cmd)
        return node_stdout, node_stderr
    
    @staticmethod
    def _parse_maintenance_windows(config_json):
        """
        Parse maintenance window configuration and return a list of dictionaries
        with day, start, end, and duration for each window.
        """
        parsed_windows = []
        
        # If string input, parse as JSON
        if isinstance(config_json, str):
            try:
                config_json = json.loads(config_json)
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON string: {e}")
                return []
        
        # Ensure we have a list to iterate over
        if not isinstance(config_json, list):
            config_json = [config_json]
        
        for config in config_json:
            if "maintenanceWindow" not in config:
                continue
            
            window = config["maintenanceWindow"]
            duration_hours = window.get("durationHours", 0)
            start_time_str = window.get("startTime", "00:00")
            utc_offset_str = window.get("utcOffset", "+00:00")
            
            # Parse schedule information
            schedule = window.get("schedule", {})
            
            # Handle weekly schedule
            if schedule and "weekly" in schedule and schedule["weekly"]:
                weekly = schedule["weekly"]
                day_of_week = weekly.get("dayOfWeek", "")
                interval_weeks = weekly.get("intervalWeeks", 1)
                
                # Create a dictionary for this window
                window_dict = {
                    "day": day_of_week,
                    "start": start_time_str,
                    "duration": duration_hours,
                    "interval_weeks": interval_weeks,
                    "utc_offset": utc_offset_str
                }
                
                # Calculate end time
                try:
                    # Parse the start time with the UTC offset
                    start_time_with_tz = parser.parse(f"{start_time_str}{utc_offset_str}")
                    
                    # Add duration to get end time
                    end_time_with_tz = start_time_with_tz + timedelta(hours=duration_hours)
                    
                    # Format end time as HH:MM
                    window_dict["end"] = end_time_with_tz.strftime("%H:%M")
                except Exception as e:
                    print(f"Error calculating end time: {e}")
                    window_dict["end"] = "Unknown"
                
                parsed_windows.append(window_dict)
            
            # Handle daily schedule
            elif schedule and "daily" in schedule and schedule["daily"]:
                daily = schedule["daily"]
                interval_days = daily.get("intervalDays", 1)
                
                # Create a dictionary for daily window
                window_dict = {
                    "day": "Daily",
                    "start": start_time_str,
                    "duration": duration_hours,
                    "interval_days": interval_days,
                    "utc_offset": utc_offset_str
                }
                
                # Calculate end time
                try:
                    start_time_with_tz = parser.parse(f"{start_time_str}{utc_offset_str}")
                    end_time_with_tz = start_time_with_tz + datetime.timedelta(hours=duration_hours)
                    window_dict["end"] = end_time_with_tz.strftime("%H:%M")
                except Exception as e:
                    print(f"Error calculating end time: {e}")
                    window_dict["end"] = "Unknown"
                
                parsed_windows.append(window_dict)
            
            # Handle monthly schedules (both absolute and relative)
            elif schedule and ("absoluteMonthly" in schedule or "relativeMonthly" in schedule):
                if "absoluteMonthly" in schedule and schedule["absoluteMonthly"]:
                    monthly = schedule["absoluteMonthly"]
                    day_of_month = monthly.get("dayOfMonth", 1)
                    interval_months = monthly.get("intervalMonths", 1)
                    
                    window_dict = {
                        "day": f"Monthly on day {day_of_month}",
                        "start": start_time_str,
                        "duration": duration_hours,
                        "interval_months": interval_months,
                        "utc_offset": utc_offset_str
                    }
                else:  # relativeMonthly
                    monthly = schedule["relativeMonthly"]
                    week_index = monthly.get("weekIndex", "First")
                    day_of_week = monthly.get("dayOfWeek", "Monday")
                    interval_months = monthly.get("intervalMonths", 1)
                    
                    window_dict = {
                        "day": f"Monthly on {week_index} {day_of_week}",
                        "start": start_time_str,
                        "duration": duration_hours,
                        "interval_months": interval_months,
                        "utc_offset": utc_offset_str
                    }
                
                # Calculate end time
                try:
                    start_time_with_tz = parser.parse(f"{start_time_str}{utc_offset_str}")
                    end_time_with_tz = start_time_with_tz + datetime.timedelta(hours=duration_hours)
                    window_dict["end"] = end_time_with_tz.strftime("%H:%M")
                except Exception as e:
                    print(f"Error calculating end time: {e}")
                    window_dict["end"] = "Unknown"
                
                parsed_windows.append(window_dict)
        return parsed_windows

    def get_maintenance_windows(self):
        config_json = self.query_maintenance_windows()
        return self._parse_maintenance_windows(config_json)

