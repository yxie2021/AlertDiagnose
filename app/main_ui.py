import streamlit as st
import subprocess
import os
import sys
import traceback
import re # Needed for parsing and sanitizing
from datetime import datetime

# --- Path Setup (Moved to top) --- #
APP_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.dirname(APP_DIR))
if ROOT_DIR not in sys.path:
    print(f"DEBUG: Adding {ROOT_DIR} to sys.path for main_ui.py")
    sys.path.insert(0, ROOT_DIR)
# --------------------------------- #

# Now imports should work
# from dependencies.utilities import parse_alert_text

# --- Configuration ---
PYTHON_EXECUTABLE = os.path.join(ROOT_DIR, ".venv", "Scripts", "python.exe")
if not os.path.exists(PYTHON_EXECUTABLE):
    print(f"Warning: Expected python path {PYTHON_EXECUTABLE} not found. Falling back to sys.executable: {sys.executable}")
    PYTHON_EXECUTABLE = sys.executable
else:
     print(f"Using Python executable: {PYTHON_EXECUTABLE}")

# Define paths relative to ROOT_DIR (which is now absolute)
ALERT_DIAGNOSE_PATH = os.path.join(APP_DIR, "diagnose_alert.py")
BASE_CHECK_SCRIPT_PATH = os.path.join(APP_DIR, "check_base_status.py") # Added path for base check script

# --- Streamlit UI ---
st.set_page_config(layout="wide")
st.title("AKS Alert Diagnoser")
st.write("Paste the full alert message below, then click 'Base Check' or 'Diagnose'.")

# Input fields
alert_text = st.text_area("Alert Info", height=300, placeholder="Paste full alert message here...")
# Restore selectbox for explicit type selection
# alert_type = st.selectbox("Alert Type", ["App Exception", "Job Failure", "Match Creation Low"])

# Place buttons side-by-side using columns
col1, col2 = st.columns([1, 5]) # Adjust ratio as needed
with col1:
    base_check_button = st.button("Base Check")
with col2:
    diagnose_button = st.button("Diagnose")
    
# Placeholder for output
output_placeholder = st.empty()

# --- Base Check Logic --- #
if base_check_button:
    if not alert_text:
        st.error("Please paste the alert information first.")
    else:
        st.info("Performing Base Check...")
        
        # Construct command for check_base_status.py
        command_list = [
            PYTHON_EXECUTABLE, 
            BASE_CHECK_SCRIPT_PATH, 
            "--alert-text", alert_text
        ]
        
        # Execute the script
        output_placeholder.code(f"Running Base Check...")
        full_output = ""
        try:
            process_env = os.environ.copy()
            existing_pythonpath = process_env.get("PYTHONPATH")
            if existing_pythonpath:
                process_env["PYTHONPATH"] = ROOT_DIR + os.pathsep + existing_pythonpath
            else:
                process_env["PYTHONPATH"] = ROOT_DIR
            
            print(f"Running command: {' '.join(command_list)} in CWD: {ROOT_DIR}")
            process = subprocess.Popen(
                command_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=ROOT_DIR,
                text=True,
                encoding='utf-8',
                errors='ignore',
                env=process_env
            )
            for line in iter(process.stdout.readline, ''):
                full_output += line
                output_placeholder.code(full_output)
            process.stdout.close()
            return_code = process.wait()
            if return_code == 0:
                st.success("Base Check script completed successfully!")
            else:
                st.error(f"Base Check script failed with return code: {return_code}")
            output_placeholder.code(full_output)
        except FileNotFoundError:
                st.error(f"Error: Could not find Python executable or script '{BASE_CHECK_SCRIPT_PATH}'. Check paths.")
        except Exception as e:
            st.error(f"An error occurred while running the Base Check script: {e}")
            tb_str = traceback.format_exc()
            error_output = full_output + f"\n--- ERROR DURING EXECUTION ---\n{e}\n\n--- TRACEBACK ---\n{tb_str}"
            output_placeholder.code(error_output)

# --- Diagnosis Logic ---
if diagnose_button:
    if not alert_text:
        st.error("Please paste the alert information first.")
    else:
        # If a script was determined (even if filename is generic)
        st.info(f"Running diagnosis script...")
        st.warning("Diagnosis may take a few minutes...")
        st.warning("Note: Check terminal for interactive prompts if needed.")
        output_placeholder.code(f"Running {os.path.basename(ALERT_DIAGNOSE_PATH)} ...")
        full_output = ""
        try:
            process_env = os.environ.copy()
            existing_pythonpath = process_env.get("PYTHONPATH")
            if existing_pythonpath:
                process_env["PYTHONPATH"] = ROOT_DIR + os.pathsep + existing_pythonpath
            else:
                process_env["PYTHONPATH"] = ROOT_DIR
            command_list = [PYTHON_EXECUTABLE, ALERT_DIAGNOSE_PATH, "--alert-text", alert_text]
            print(f"Running command: {' '.join(command_list)} in CWD: {ROOT_DIR}")
            process = subprocess.Popen(
                command_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=ROOT_DIR,
                text=True,
                encoding='utf-8',
                errors='ignore',
                env=process_env
            )
            for line in iter(process.stdout.readline, ''):
                full_output += line
                output_placeholder.code(full_output)
            process.stdout.close()
            return_code = process.wait()
            if return_code == 0:
                st.success("Diagnosis script completed successfully!")
            else:
                st.error(f"Diagnosis script failed with return code: {return_code}")
            output_placeholder.code(full_output)
        except FileNotFoundError:
            st.error(f"Error: Could not find Python executable at '{PYTHON_EXECUTABLE}' or script '{ALERT_DIAGNOSE_PATH}'. Check paths.")
        except Exception as e:
            st.error(f"An error occurred while running the diagnosis script: {e}")
            tb_str = traceback.format_exc()
            error_output = full_output + f"\n--- ERROR DURING EXECUTION ---\n{e}\n\n--- TRACEBACK ---\n{tb_str}"
            output_placeholder.code(error_output)
  