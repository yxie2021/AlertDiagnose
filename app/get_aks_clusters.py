import os
import json
import sys

from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
from azure.mgmt.containerservice import ContainerServiceClient
from dependencies.utilities import login_to_azure

FILE_PATH = "dependencies/cluster_info.json"

def get_aks_clusters():
    """Uses login_to_azure helper to get SDK credential, then lists clusters."""
    print("--- Running get_aks_clusters --- ")
    
    # 1. Ensure Login & Get SDK Credential via Helper
    # Assumes login_to_azure now returns (bool, str, credential_object | None)
    print("Ensuring Azure login and obtaining SDK credential via helper...")
    login_success, login_message, credential = login_to_azure()
    # print(f"Login check result: {login_message}") # Reduced verbosity
    if not login_success or not credential:
        print("Exiting: Azure login/credential retrieval failed.")
        return []
    print("Login/Credential check successful.") # Concise success message
        
    # 2. List Subscriptions and Clusters using SDK (with credential from helper)
    print("Listing subscriptions and clusters via Azure SDK...")
    try:
        # Use the credential object obtained from the helper function
        subscription_client = SubscriptionClient(credential)
        subscriptions = list(subscription_client.subscriptions.list())
        print(f"Found {len(subscriptions)} subscriptions accessible via current login.")
    except Exception as e:
        print(f"Error listing subscriptions via SDK: {e}")
        return []

    all_clusters_info = []
    print("Processing subscriptions...") # Added high-level progress
    for sub in subscriptions:
        sub_id = sub.subscription_id
        sub_name = sub.display_name 
        # print(f"\nChecking subscription: {sub_name} ({sub_id})") # Reduced verbosity

        try:
            # Initialize clients with the credential object for each subscription
            resource_client = ResourceManagementClient(credential, sub_id)
            container_service_client = ContainerServiceClient(credential, sub_id)

            resource_groups = list(resource_client.resource_groups.list())
            # print(f"Found {len(resource_groups)} resource groups in subscription {sub_id}.") # Reduced verbosity

            for rg in resource_groups:
                rg_name = rg.name
                try:
                    aks_clusters = list(container_service_client.managed_clusters.list_by_resource_group(rg_name))
                    if aks_clusters:
                        # print(f"    Found {len(aks_clusters)} AKS cluster(s) in resource group: {rg_name}.") # Optional detail
                        for cluster in aks_clusters:
                            cluster_info = {
                                "subscription_id": sub_id,
                                "subscription_name": sub_name, 
                                "resource_group": rg_name,
                                "aks_cluster_name": cluster.name
                            }
                            all_clusters_info.append(cluster_info)
                except Exception as e:
                    # Keep warning for cluster listing errors
                    print(f"    Warning: Error listing AKS clusters in RG '{rg_name}' (Sub: '{sub_name}'): {e}")

        except Exception as e:
            # Keep warning for subscription processing errors
            print(f"Error processing subscription '{sub_name}' ({sub_id}) via SDK: {e}")

    print(f"Finished processing subscriptions. Found {len(all_clusters_info)} total AKS clusters.") # Summary
    return all_clusters_info

def save_to_json(data, file_path=FILE_PATH):
    """Saves the provided data to a JSON file. """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f: 
            json.dump(data, f, indent=4)
        print(f"Successfully saved cluster information to {file_path}") # Keep confirmation
    except Exception as e:
        print(f"Error saving data to JSON file {file_path}: {e}")

if __name__ == "__main__":
    clusters = get_aks_clusters()
    if clusters:
        save_to_json(clusters)
    else:
        # Keep this message for clarity when no clusters are found/saved
        print("No AKS clusters found or an error occurred during retrieval. JSON file not updated.") 