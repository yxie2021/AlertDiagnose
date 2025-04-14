# AlertDiagnose
Simple python 3.12 streamlit app to quickly identify AKS service related alert

Background:
1. dependencies/cluster_info.json stores the Azure subscription and resource_group information about an AKS cluster. 
If this file is out of date, run app/get_aks_cluster.py to regenerate the file.
2. Use command: <python.exe> -m streamlit run app/main_ui.py.  It will launch the UI in the browser (normally: http://localhost:8503/)
3. How to use:
	a. Copy the alert text to the textbox in the UI.  The program will parse the alert text to find information about cluster, namespace, app/job name etc.  
	b. Once it obtain the required cluster name, it will run Azure CLI login and set up proper Azure/KubeCtl context for following checks.  
	   By default, it will use the current Azure login information.  If not user is not currently logged in Azure, it will open browser page to for authentication.
	c. Click "Base Check" button to check basic status of the cluster/namespace, which include:
		Is game in limited mode?
		Node pool status (validate no failure)
		Node status (vlaidate all in same version)
		Maintenance Window
		Analyze AKS cluster event log
	d. Click "Diagnose" to get more information about affected cluster/namespace:
		Execute kubectl describe <app/job/pod>
		Execute kubectl to get log for the associated pods.  If pods has been restarted, it will also obtain the previous log for troubleshooting
		Output from diagnose can be found under the project output folder.  
		
		
	
