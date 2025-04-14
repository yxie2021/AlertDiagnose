import os
import subprocess
import json
import sys # Keep sys import for potential future platform checks if needed

# Note: Consider adding find_executable_path here too if needed by login_to_azure
# For now, assuming 'az' is findable by subprocess based on diagnose_exception.py logic

import os
import json
import re
from azure.identity import AzureCliCredential, UsernamePasswordCredential, InteractiveBrowserCredential

def _ensure_az_path(az_path: str = None):
    if not az_path:
        az_path = find_executable_path("az.cmd") # Or just "az"
        if not az_path: 
            raise Exception("Azure CLI executable not found")
    return az_path

def login_to_azure(az_path: str = None):
    """
    Log in to Azure and return a credential object that can be used with Azure SDK clients.
    
    Attempts login in the following order:
    1. Use existing/default login via AzureCliCredential
    2. Use credentials from environment variables with UsernamePasswordCredential
    3. Fallback to interactive login with AzureCliCredential or InteractiveBrowserCredential
    
    Returns:
        tuple: (success_status: bool, output_or_error_message: str, credential: Azure credential object or None)
    """
    try:
        az_path = _ensure_az_path(az_path)
        # First try to use AzureCliCredential (if already logged in)
        try:
            # Check if already logged in to Azure CLI
            check_cmd = [az_path, "account", "show"]
            result = subprocess.run(check_cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                # Already logged in, create AzureCliCredential
                credential = AzureCliCredential()
                # Test the credential with a token request
                credential.get_token("https://management.azure.com/.default")
                
                account_info = json.loads(result.stdout)
                return True, f"Using existing login as {account_info.get('user', {}).get('name', 'Unknown user')}", credential
        except Exception as e:
            # Continue to next method if this fails
            pass
        
        # Try interactive Azure CLI login
        print("Not currently logged in azure. Attempting interactive login via Azure CLI...")
        interactive_cmd = [az_path, "login"]
        interactive_result = subprocess.run(interactive_cmd, capture_output=True, text=True)
        
        if interactive_result.returncode == 0:
            try:
                # Create AzureCliCredential after successful interactive login
                credential = AzureCliCredential()
                # Test the credential
                credential.get_token("https://management.azure.com/.default")
                
                return True, "Successfully logged in using interactive CLI method", credential
            except Exception as e:
                # Continue to next method if this fails
                pass
        
        # As a last resort, try browser-based interactive authentication
        try:
            print("Attempting browser-based interactive login...")
            credential = InteractiveBrowserCredential()
            # Force a token request to verify credential works
            credential.get_token("https://management.azure.com/.default")
            
            return True, "Successfully logged in using browser-based interactive method", credential
        except Exception as e:
            return False, f"Failed to authenticate using all available methods. Last error: {str(e)}", None
            
    except Exception as e:
        return False, f"Error during login process: {str(e)}", None

def get_azure_token(az_path: str = None):
    """
    Retrieves the access token for the currently authenticated Azure session using 'az account get-access-token'.
    
    Returns:
        str or None: The access token if successful, None otherwise
    """
    try:
        az_path = _ensure_az_path(az_path)
        # token_cmd = [az_path, "account", "get-access-token", "--output", "json"]
        token_cmd = ["az", "account", "get-access-token", "--output", "json"]
        # print("\nAttempting to get access token using 'az account get-access-token'...")
        token_result = subprocess.run(token_cmd, capture_output=True, text=True, encoding='utf-8')
        
        if token_result.returncode == 0:
            token_info = json.loads(token_result.stdout)
            token = token_info.get("accessToken")
            if token:
                 # print("Successfully retrieved access token.")
                 return token
            else:
                 print("Warning: 'az account get-access-token' succeeded but token was empty.")
                 return None
        else:
            print(f"Error getting access token: {token_result.stderr.strip()}")
            return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from 'az account get-access-token': {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while getting access token: {e}")
        return None 
    
def find_executable_path(executable_name):
    """
    Uses 'where' command on Windows to find the full path of an executable.
    executable_name should include the extension
    """
    if sys.platform != "win32":
        print(f"Warning: 'find_executable_path' relies on 'where' command (Windows only). Trying '{executable_name}' directly.")
        return executable_name

    # On Windows, prefer .cmd or .bat if looking for 'az'
    search_name = executable_name
    try:
        # print(f"Locating '{search_name}' executable using 'where' command...")
        result = subprocess.run(["where", search_name], capture_output=True, text=True, check=True, encoding='utf-8')
        paths = result.stdout.strip().splitlines()
        if paths:
            first_path = paths[0].strip()
            # print(f"Found '{search_name}' at: {first_path}")
            return first_path
        else:
            # print(f"Warning: 'where {search_name}' ran but returned no paths.")            
            return None
    except FileNotFoundError:
        print(f"Error: 'where' command not found. Cannot locate '{search_name}'.")
        return None
    except subprocess.CalledProcessError:
        print(f"Error: 'where' command could not find '{search_name}'. Is it installed and in PATH?")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while running 'where {search_name}': {e}")
        return None
    
def run_command(command, shell=False, check=True):
    """Runs a command using subprocess and returns its output."""
    # print(f"\nRunning command: {' '.join(command) if isinstance(command, list) else command}")
    try:
        # result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        result = subprocess.run(command, capture_output=True, text=True, shell=shell, check=check, encoding='utf-8')
        #print("Command successful.")
        return result.stdout.strip(), result.stderr.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {' '.join(command) if isinstance(command, list) else command}")
        print(f"Return code: {e.returncode}, stdout: {e.stdout}, stderr: {e.stderr}")
        return None, e.stderr
    except FileNotFoundError:
        print(f"Error: Command not found (ensure Azure CLI and kubectl are installed and in PATH): {command[0]}")
        return None, f"Command not found: {command[0]}"
    except Exception as e:
        print(f"An unexpected error occurred while running command '{command[0]}': {e}")
        return None, str(e) 
    
def get_cluster_info(cluster_name):
    """
    Given cluster name, load the cluster_info.json to figure out the subscription_id and resource_group
    """
    cluster_info_path = "dependencies/cluster_info.json"
    # print(f"Loading cluster info from '{cluster_info_path}'...")
    try:
        with open(cluster_info_path, 'r', encoding='utf-8') as f:
            cluster_data =  json.load(f)
    except FileNotFoundError:
        print(f"Error: Cluster info file not found at '{cluster_info_path}'")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{cluster_info_path}'")
        return None
    except Exception as e:
        print(f"Error reading cluster info file '{cluster_info_path}': {e}")
        return None

    for cluster_entry in cluster_data:
        if cluster_entry.get('aks_cluster_name', '').lower() == cluster_name.lower():
            subscription_id = cluster_entry.get('subscription_id')
            resource_group = cluster_entry.get('resource_group')
            cluster_info ={"subscription_id": subscription_id, "resource_group": resource_group}
            return cluster_info


    raise Exception(f"Error: Cluster '{cluster_name}' not found or missing details in {cluster_info_path}")
    return None

def setup_az_context(subscription_id, resource_group, cluster_name, az_path: str = None):
    az_path = _ensure_az_path(az_path)
    # print("Attempting Azure Login...")
    login_success, login_message, credential = login_to_azure(az_path=az_path)
    print(f"Azure Login attempt result: {login_message}")
    if not login_success or not credential:
        print("Setup failed: Azure login/credential retrieval failed.")
        return False

    # print("\n Setting Azure Subscription via CLI...")

    set_cmd = [az_path, "account", "set", "--subscription", subscription_id]
    stdout_set, stderr_set = run_command(set_cmd)
    if stdout_set is None and stderr_set is not None:
        print(f"Setup failed: Failed to set Azure subscription '{subscription_id}'. Error: {stderr_set}")
        return False
    elif stderr_set:
        print(f"Warning while setting subscription: {stderr_set}")

    # Get AKS Credentials (via CLI)
    # print("\nGetting AKS Credentials via CLI...")
    cred_cmd = [az_path, "aks", "get-credentials", "--resource-group", resource_group, "--name", cluster_name, "--overwrite-existing"]
    stdout_cred, stderr_cred = run_command(cred_cmd)
    if stdout_cred is None and stderr_cred is not None:
        print(f"Setup failed: Failed to get AKS credentials for cluster '{cluster_name}'. Error: {stderr_cred.strip()}")
        return False
    elif stderr_cred:
        print(f"Warning while getting AKS credentials: {stderr_cred.strip()}")

    print(f"Context setup complete for resource group '{resource_group}' and cluster '{cluster_name}'.")

    return True

def parse_alert_text(alert_content: str) -> dict:
    """Parses raw alert text to find key details like app or job name."""
    details = {}
    target_keys = ['cluster', 'namespace', 'app','container','deployment','instance', 'job', 'job_name', 'pod', 'service', 'alertname', 'reason']
    try:
        for key in target_keys:
            pattern_key_name = key.replace('_', ' ') 
            match = re.search(rf"(?:•\s*)?(?:{key}|{pattern_key_name}):\s*([^\n]+)", alert_content, re.IGNORECASE | re.MULTILINE)
            if match:
                value = match.group(1).strip()
                if '" in ' in value:
                    value = value.split('" in ')[0].strip()
                details[key] = value
        if 'cluster' not in details:
            print(f"Error: Cluster not found in alert text. Alert text: {alert_content}")
            return None
        # now load the cluster_info.json and get the cluster_name, and fill in the details with subscription_id and resource_group
        cluster_info = get_cluster_info(details['cluster'])
        if cluster_info:
            details['subscription_id'] = cluster_info.get('subscription_id')
            details['resource_group'] = cluster_info.get('resource_group')
        # print(f"  Found {key}: {value}")
    except Exception as e:
        print(f"An error occurred during alert text parsing: {e}") 
    return details

def parse_alert_file(file_path: str):
    """
    Extract alertname, app, cluster, and namespace from an alert text file.
    (Using the version you finalized)
    Args:
        file_path (str): Path to the file containing the alert text
    Returns:
        dict: Dictionary containing the extracted information, or None if required keys missing.
    """
    # target_keys = {'alertname', 'app', 'cluster', 'namespace'}
    details = {}
    print(f"parse_alert_file: {file_path}")
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        details = parse_alert_text(content)
        return details
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return None
    except Exception as e:
        print(f"An error occurred during parsing: {str(e)}")
        return None
    
def has_required_keys(d: dict, required_keys: list) -> bool:
    return all(key in d for key in required_keys)