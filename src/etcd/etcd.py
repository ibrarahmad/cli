#!/usr/bin/env python3
#     Copyright (c)  2022-2024 PGEDGE  #

import subprocess
import os
import fire
import util
import json
import sys
from datetime import datetime
from tabulate import tabulate
import re

def osSys(p_input, p_output=False, p_display=True):
    if p_display:
        print("# " + p_input)
    result = subprocess.run(p_input.split(), capture_output=True, text=True)
    if p_output:
        print (result.stdout)
    else:
        printb("Command failed.")

    return result

def printb(message, end="\n"):
    print(f"\033[1m{message}\033[0m", end=end)

def service_status():
    service_name = "etcd"
    try:
        # Run the systemctl command to check service status
        result = osSys(f"systemctl status {service_name}", False, False)
        if result.returncode == 0:
            # Parse the output to determine the status
            output_lines = result.stdout.split('\n')
            for line in output_lines:
                if 'Active:' in line:
                    status = line.split(':')[1].strip()
                    print(f"\nChecking etcd service status ", end="...")
                    printb("[Active]")
                    return status
            # If status not found, return unknown
            print(f"\nChecking etcd service status ", end="...")
            printb(f"[Stopped/Failed]")
            return 'Unknown'
        else:
            print(f"\nChecking etcd service status ", end="...")
            printb(f"[Stopped/Failed]")
            # If the command failed, return None
            return None
    except Exception as e:
        print("Error:", e)
        return None

def run_external_command(*args):
    """
    Run etcd with the given arguments.
    Automatically prepends 'etcd' to the arguments.
    """
    # Prepend 'etcd' to the command arguments
    command = ["etcd"] + list(args)
    try:
        # Execute the command and capture the output
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # If the command was successful, print the stdout
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        # If an error occurred, print the stderr
        print(f"Error executing command: {e.stderr}")

def node_add(node_name, node_ip):
    """
    Add a new node to the etcd cluster.

    Parameters:
        node_name (str): The hostname of the new node.
        node_ip (str): The IP address of the new node.

    """
    # Regular expression pattern to validate hostname
    hostname_pattern = r'^[a-zA-Z0-9][a-zA-Z0-9.-]{1,253}$'
    # Regular expression pattern to validate IP address
    ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'

    if re.match(hostname_pattern, node_name) and re.match(ip_pattern, node_ip):
        osSys(f"etcdctl member add {node_name} --peer-urls=http://{node_ip}:2380")
    else:
        print("Usage: node_add <node_name> <node_ip>")
        print("Ensure that the provided hostname and IP address are in the correct format.")

def node_remove(node_name):
    """
    Remove a node from the etcd cluster.

    Parameters:
        node_name (str): The name of the node to be removed.

    """
    # Regular expression pattern to validate hostname
    hostname_pattern = r'^[a-zA-Z0-9][a-zA-Z0-9.-]{1,253}$'
    # Regular expression pattern to validate IP address
    ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'

    if re.match(hostname_pattern, node_name):
        osSys(f"etcdctl member remove {node_name}")
    else:
        print("Usage: etcd_node_remove <node_name>")
        print("Ensure that the provided node name is in the correct format.")

def cleanup():
    """Cleanup cluster."""
    osSys("sudo systemctl stop etcd")
    osSys("sudo rm -rf /var/lib/etcd/postgresql")

def start():
    """Start the etcd service."""
    osSys("sudo systemctl start etcd")

def stop():
    """Stop the etcd service."""
    osSys("sudo systemctl stop etcd")

def status():
    """Status of etcd cluster"""
    osSys("etcdctl endpoint status --write-out=table", True, False)

def list():
    """List of nodes of etcd cluster"""
    osSys("etcdctl member list --write-out=table", True, False)

if __name__ == "__main__":
    fire.Fire({
        "node-add": node_add,
        "node-remove": node_remove,
        "start": start,
        "stop": stop,
        "cleanup": cleanup,
        "service-status": service_status,
        "status": status,
        "list": list,
        "command": run_external_command,
    })

