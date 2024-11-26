
#  Copyright 2022-2024 PGEDGE  All rights reserved. #

import os
import json
import datetime
import util
import fire
import meta
import time
import sys
import getpass
from tabulate import tabulate
from ipaddress import ip_address
try:
    import etcd
    import ha_patroni
except Exception:
    pass

BASE_DIR = "cluster"
DEFAULT_REPO = "https://pgedge-download.s3.amazonaws.com/REPO"

def run_cmd(cmd, node, message, verbose, capture_output=False, ignore=False, important=False):
    """
    Run a command on a remote node via SSH.

    Args:
        cmd (str): The command to run.
        node (dict): The node information.
        message (str): Message to display.
        verbose (bool): Verbose output.
        capture_output (bool): Capture command output.
        ignore (bool): Ignore errors.
        important (bool): Important command.

    Returns:
        result: The result of the command execution.
    """
    name = node["name"]
    message = name + " - " + message
    return util.run_rcommand(
        cmd=cmd,
        message=message,
        host=node["public_ip"],
        usr=node["os_user"],
        key=node["ssh_key"],
        verbose=verbose,
        capture_output=capture_output,
        ignore=ignore,
        important=important
    )

def ssh(cluster_name, node_name):
    """An SSH Terminal session into the specified node"""
    json_validate(cluster_name)
    cluster = load_json(cluster_name)

    for nd in cluster["node_groups"]:
        if node_name == nd["name"]:
            ip = nd["public_ip"] if "public_ip" in nd else nd["private_ip"]
            if not ip:
                util.exit_message(f"Node '{node_name}' does not have a valid IP address.")
            util.echo_cmd(
                f'ssh -i {nd["ssh"]["private_key"]} {nd["ssh"]["os_user"]}@{ip}'
            )
            util.exit_cleanly(0)

    util.exit_message(f"Could not locate node '{node_name}'")


def set_firewalld(cluster_name):
    """ Open up nodes only to each other on pg port (WIP)"""
    
    ## install & start firewalld if not present
    rc = util.echo_cmd("sudo firewall-cmd --version")
    if rc != 0:
       rc = util.echo_cmd("sudo dnf install -y firewalld")
       rc = util.echo_cmd("sudo systemctl start firewalld")

    db, db_settings, nodes = load_json(cluster_name)

    for nd in nodes:
       util.message(f'OUT name={nd["name"]}, ip_address={nd["public_ip"]}, port={nd["port"]}', "info")
       out_name = nd["name"]
       for in_nd in nodes:
          if in_nd["name"] != out_name:
             print(f'   IN    name={in_nd["name"]}, ip_address={in_nd["public_ip"]}, port={in_nd["port"]}')


def get_cluster_info(cluster_name, create=True):
    """Returns the cluster directory and file path for a given cluster name."""
    cluster_dir = os.path.join(util.MY_HOME, BASE_DIR, cluster_name)
    cluster_file = os.path.join(cluster_dir, f"{cluster_name}.json")

    if create:
        os.makedirs(cluster_dir, exist_ok=True)

    return cluster_dir, cluster_file


def get_cluster_json(cluster_name):
    """Load the cluster JSON configuration file."""
    cluster_dir, cluster_file = get_cluster_info(cluster_name, False)

    if not os.path.isdir(cluster_dir):
        util.exit_message(f"Cluster directory '{cluster_dir}' not found")

    if not os.path.isfile(cluster_file):
        util.message(f"Cluster file '{cluster_file}' not found", "warning")
        return None

    try:
        with open(cluster_file, "r") as f:
            return json.load(f)
    except Exception as e:
        util.exit_message(
            f"Unable to load cluster def file '{cluster_file}\n{e}")


def write_cluster_json(cluster_name, cj):
    """Write the updated cluster configuration to the JSON file."""
    cluster_dir, cluster_file = get_cluster_info(cluster_name)
    cj["update_date"] = datetime.datetime.now().astimezone().isoformat()
    try:
        cjs = json.dumps(cj, indent=2)
        util.message(f"write_cluster_json {cluster_name}, {cluster_dir}, "
                     f"{cluster_file},\n{cjs}", "debug")
        with open(cluster_file, "w") as f:
            f.write(cjs)
    except Exception as e:
        util.exit_message(
            f"Unable to write_cluster_json {cluster_file}\n{str(e)}")


def load_json(cluster_name):
    """
    Load a JSON config file for a cluster.

    Args:
        cluster_name (str): The name of the cluster.

    Returns:
        tuple: (db, db_settings, nodes)
    """

    parsed_json = get_cluster_json(cluster_name)
    if parsed_json is None:
        util.exit_message("Unable to load cluster JSON")

    # Extract database settings
    pgedge = parsed_json.get("pgedge", {})
    db_settings = {
        "pg_version": pgedge.get("pg_version", ""),
        "spock_version": pgedge.get("spock", {}).get("spock_version", ""),
        "auto_ddl": pgedge.get("spock", {}).get("auto_ddl", "off"),
        "auto_start": pgedge.get("auto_start", "on")
    }

    db = []
    if "databases" not in pgedge:
        util.exit_message("databases key is missing")

    for database in pgedge.get("databases"):
        if set(database.keys()) != {"db_name", "db_user", "db_password"}:
            util.exit_message("Each database entry must contain db_name, db_user, and db_password")

        db.append({
            "db_name": database["db_name"],
            "db_user": database["db_user"],
            "db_password": database["db_password"]
        })


    # Extract node information
    nodes = []
    for group in parsed_json.get("node_groups", []):
        ssh_info = group.get("ssh", {})
        os_user = ssh_info.get("os_user", "")
        ssh_key = ssh_info.get("private_key", "")

        node_info = {
            "name": group.get("name", ""),
            "is_active": group.get("is_active", ""),
            "public_ip": group.get("public_ip", ""),
            "private_ip": group.get("private_ip", ""),
            "port": group.get("port", ""),
            "path": group.get("path", ""),
            "os_user": os_user,
            "ssh_key": ssh_key,
            "backrest": group.get("backrest", {})
        }

        if not node_info["public_ip"] and not node_info["private_ip"]:
            util.exit_message(f"Node '{node_info['name']}' must have either a public_ip or private_ip defined.")
       

        # Process sub_nodes
        sub_node_list=[]
        for sub_node in group.get("sub_nodes", []):
            sub_node_info = {
                "name": sub_node.get("name", ""),
                "is_active": sub_node.get("is_active", ""),
                "public_ip": sub_node.get("public_ip", ""),
                "private_ip": sub_node.get("private_ip", ""),
                "port": sub_node.get("port", ""),
                "path": sub_node.get("path", ""),
                "os_user": os_user,
                "ssh_key": ssh_key
            }

            if not sub_node_info["public_ip"] and not sub_node_info["private_ip"]:
                util.exit_message(f"Sub-node '{sub_node_info['name']}' must have either a public_ip or private_ip defined.")
            sub_node_list.append(sub_node_info)
        node_info["sub_nodes"] = (sub_node_list)

        nodes.append(node_info)

    return db, db_settings, nodes

def save_updated_json(cluster_name, updated_json):
    """
    Save the updated JSON configuration back to the appropriate file.
 
    Args:
        cluster_name (str): The name of the cluster.
        updated_json (dict): The updated JSON data to be saved.
    """
    # Define the path to the JSON file
    cluster_path = f"cluster/{cluster_name}/{cluster_name}.json"

    # Ensure the directory exists
    directory = os.path.dirname(cluster_path)
    if not os.path.exists(directory):
        os.makedirs(directory)

    # Save the updated JSON to the file
    with open(cluster_path, 'w') as json_file:
        json.dump(updated_json, json_file, indent=4)
    print(f"Updated JSON saved to {cluster_path}")

def json_validate(cluster_name):
    """Validate and update a Cluster Configuration JSON file"""
    parsed_json = get_cluster_json(cluster_name)

    # Initialize a summary dictionary
    summary = {
        "cluster_name": cluster_name,
        "total_nodes": 0,
        "node_details": [],
        "subnodes_info": []
    }

    # Check for required top-level keys
    required_top_keys = ["cluster_name", "pgedge", "node_groups"]
    for key in required_top_keys:
        if key not in parsed_json:
            util.exit_message(f"{key} is missing")
 
    # Ensure pgedge section is complete
    pgedge_defaults = {
        "pg_version": "16",
        "spock": {"spock_version": "4.0.5"},
        "databases": []
    }
    if "pgedge" not in parsed_json:
        parsed_json["pgedge"] = pgedge_defaults
 
    # Ensure json_version is correct
    if parsed_json.get("json_version") != "1.1":
        parsed_json["json_version"] = "1.1"

    # Validate and update node_groups
    for idx, node in enumerate(parsed_json.get("node_groups", [])):
        summary["total_nodes"] += 1  # Increment total node count
        node_info = {
            "node_index": idx + 1,  # Start numbering nodes from 1
            "public_ip": node.get("public_ip", ""),
            "private_ip": node.get("private_ip", ""),
            "port": node.get("port", 5432),
            "is_active": node.get("is_active", "off"),
            "path": node.get("path", "/var/lib/postgresql"),
        }

        # Validate subnodes
        sub_nodes = node.get("sub_nodes", [])
        subnode_count = len(sub_nodes) if isinstance(sub_nodes, list) else 0
        if subnode_count > 0:
            subnode_info = f"Node {idx + 1} Subnodes: {subnode_count}"  # Start numbering subnodes from 1
        else:
            subnode_info = f"Node {idx + 1} Subnodes: None"
        summary["subnodes_info"].append(subnode_info)

        # Append node details
        summary["node_details"].append(node_info)

    # Save updated JSON
    save_updated_json(cluster_name, parsed_json)
 
    # Gather all lines for determining the maximum width
    lines = []
    lines.append(f"#  Updated JSON saved to cluster/{cluster_name}/{cluster_name}.json")
    lines.append(f"Cluster Name: {summary['cluster_name']}")
    lines.append(f"Total Nodes: {summary['total_nodes']}")
    lines.append("Node Details:")
    for node in summary["node_details"]:
        lines.append(f"  Node {node['node_index']}: Public IP={node['public_ip']}, "
                     f"Private IP={node['private_ip']}, Port={node['port']}, "
                     f"Active={node['is_active']}, Path={node['path']}")
    lines.append("Subnodes Info:")
    for subnode in summary["subnodes_info"]:
        lines.append(f"  {subnode}")

  # Determine the maximum line length
    max_length = 50
    bold_start = "\033[1m"
    bold_end = "\033[0m"

    # Create the dynamic border
    border = "#" * (max_length + 2)  # Add 2 for padding

    # Display the updated summary
    print(border)
    print(f"# {bold_start}Cluster JSON cluster/{cluster_name}/{cluster_name}.json validated {bold_end}")
    print(f"# {bold_start}Cluster Name{bold_end}       : {summary['cluster_name']}")
    print(f"# {bold_start}Number of Nodes{bold_end}    : {summary['total_nodes']}")
    for node in summary["node_details"]:
        print(f"# {bold_start}Node {node['node_index']}{bold_end}")
        print(f"#      {bold_start}Public IP{bold_end}     : {node['public_ip']}")
        print(f"#      {bold_start}Private IP{bold_end}    : {node['private_ip']}")
        print(f"#      {bold_start}Port{bold_end}          : {node['port']}")
        print(f"#      {bold_start}Replicas{bold_end}      : {node.get('replicas', 'N/A')}")
    print(border)

def ssh_setup(cluster_name, db, db_settings, db_user, db_passwd, n, install):
    REPO = os.getenv("REPO", "")
    ndnm = n["name"]
    ndpath = n["path"]
    ndip = n["public_ip"]
    pg = db_settings["pg_version"]
    spock = db_settings["spock_version"]
    verbose = db_settings.get("log_level", "info")
    try:
        ndport = str(n["port"])
    except Exception:
        ndport = "5432"

    nc = os.path.join(ndpath, "pgedge", "pgedge ")
    parms = f" -U {db_user} -P {db_passwd} -d {db} --port {ndport}"
    if pg is not None and pg != '':
        parms = parms + f" --pg {pg}"
    if spock is not None and spock != '':
        parms = parms + f" --spock_ver {spock}"
    if db_settings["auto_start"] == "on":
        parms = f"{parms} --autostart"
    
    cmd = f"{nc} setup {parms}"
    message = f"Setup pgedge"
    run_cmd(cmd, n, message=message, verbose=verbose)
        
    if db_settings["auto_ddl"] == "on":
        cmd = nc + " db guc-set spock.enable_ddl_replication on;"
        cmd = cmd + " " + nc + " db guc-set spock.include_ddl_repset on;"
        cmd = cmd + " " + nc + " db guc-set spock.allow_ddl_from_functions on;"
        
        message = f"Setup spock"
        run_cmd(cmd, n, message=message, verbose=verbose)
        
    if db_settings["auto_ddl"] == "on":
        util.message("#")
    return 0

def ssh_install(cluster_name, db, db_settings, db_user, db_passwd, n, install):
    if install is None: 
        install=True
    REPO = os.getenv("REPO", "")
    ndnm = n["name"]
    ndpath = n["path"]
    ndip = n["public_ip"]
    pg = db_settings["pg_version"]
    spock = db_settings["spock_version"]
    try:
        ndport = str(n["port"])
    except Exception:
        ndport = "5432"

    if REPO == "":
        REPO = DEFAULT_REPO
        os.environ["REPO"] = REPO

    verbose = db_settings.get("log_level", "info")
    if install == True:  
        print_install_hdr(cluster_name, db, db_user, len(n), n["name"],
                          n["path"], ndip, n["port"], REPO)

        install_py = "install.py"      
        
        message = f"Installing pgedge"
        cmd0 = f"export REPO={REPO}; "
        cmd1 = f"mkdir -p {ndpath}; cd {ndpath}; "
        cmd2 = f'python3 -c "\\$(curl -fsSL {REPO}/{install_py})"'
        run_cmd(cmd0 + cmd1 + cmd2, n, message=message, verbose=verbose)    

    nc = os.path.join(ndpath, "pgedge", "pgedge ")
    cmd = f"{nc} install pg{pg}"
    
    message=f"Installing pg{pg} on {ndnm}"
    run_cmd(cmd, n, message=message, verbose=verbose)
    
    return 0


def ssh_cross_wire_pgedge(cluster_name, db, db_settings, db_user, db_passwd,
                          nodes, verbose):
    """
    Create nodes and subscriptions on every node in a cluster.

    Args:
        cluster_name (str): The name of the cluster.
        db (str): The database name.
        db_settings (dict): Database settings.
        db_user (str): The database user.
        db_passwd (str): The database password.
        nodes (list): The list of nodes.
        verbose (bool): Verbose output.
    """
    sub_array = []
    for prov_n in nodes:
        ndnm = prov_n["name"]
        ndpath = prov_n["path"]
        nc = os.path.join(ndpath, "pgedge", "pgedge")
        ndip = prov_n["private_ip"] if prov_n["private_ip"] else prov_n["public_ip"]
        os_user = prov_n["os_user"]
        ssh_key = prov_n["ssh_key"]

        try:
            ndport = str(prov_n["port"])
        except KeyError:
            ndport = "5432"

        cmd1 = (f"{nc} spock node-create {ndnm} "
                f"'host={ndip} user={os_user} "
                f"dbname={db} port={ndport}' {db}")
        message = f"Creating node {ndnm}"
        run_cmd(cmd1, prov_n, message=message, verbose=verbose)

        for sub_n in nodes:
            sub_ndnm = sub_n["name"]
            if sub_ndnm != ndnm:
                sub_ndip = sub_n["private_ip"] if sub_n["private_ip"] else sub_n["public_ip"]
                sub_name = f"sub_{ndnm}{sub_ndnm}"
                cmd = f"{nc} spock sub-create {sub_name} 'host={sub_ndip} user={os_user} dbname={db} port={sub_n['port']}' {db}"
                sub_array.append([cmd, ndip, os_user, ssh_key, prov_n, sub_name])

    for n in sub_array:
        cmd = n[0]
        node = n[4]
        sub_name = n[5]
        message = f"Creating subscriptions {sub_name}"
        run_cmd(cmd, node, message=message, verbose=verbose)

    cmd = f"{nc} spock node-list {db}"
    message = "Listing spock nodes"
    result = run_cmd(cmd, prov_n, message=message, verbose=verbose,
                     capture_output=True)

    print("\n")
    print(result.stdout)


def ssh_install_pgedge(cluster_name, db, db_settings, db_user, db_passwd, nodes, install, verbose):
    """
    Install and configure pgEdge on a list of nodes.

    Args:
        cluster_name (str): The name of the cluster.
        db_name (str): The database name.
        db_settings (dict): Database settings.
        db_user (str): The database user.
        db_password (str): The database user password.
        nodes (list): The list of nodes.
        verbose (bool): Verbose output.
    """
    if install is None: 
        install=True
    for n in nodes:
        REPO = os.getenv("REPO", "")
        print("\n")
        print_install_hdr(cluster_name, db, db_user, len(nodes), n["name"], n["path"], n["public_ip"], n["port"], REPO)
        ndnm = n["name"]
        ndpath = n["path"]
        ndip = n["public_ip"]
        pg = db_settings["pg_version"]
        spock = db_settings["spock_version"]  
        try:
            ndport = str(n["port"])
        except Exception:
            ndport = "5432"

        if REPO == "":
            REPO = DEFAULT_REPO
            os.environ["REPO"] = REPO

        if install == True:  
            install_py = "install.py"

            cmd0 = f"export REPO={REPO}; "
            cmd1 = f"mkdir -p {ndpath}; cd {ndpath}; "
            cmd2 = f'python3 -c "\\$(curl -fsSL {REPO}/{install_py})"'
   
            message = f"Installing pgedge"
            run_cmd(cmd0 + cmd1 + cmd2, n, message=message, verbose=verbose)

        nc = os.path.join(ndpath, "pgedge", "pgedge ")
        parms = f" -U {db_user} -P {db_passwd} -d {db} --port {ndport}"
        if pg is not None and pg != '':
            parms = parms + f" --pg {pg}"
        if spock is not None and spock != '':
            parms = parms + f" --spock_ver {spock}"
        if db_settings["auto_start"] == "on":
            parms = f"{parms} --autostart"
    
        cmd = f"{nc} setup {parms}"
        message = f"Setup pgedge"
        run_cmd(cmd, n, message=message, verbose=verbose)
        
        if db_settings["auto_ddl"] == "on":
            cmd = nc + " db guc-set spock.enable_ddl_replication on;"
            cmd = cmd + " " + nc + " db guc-set spock.include_ddl_repset on;"
            cmd = cmd + " " + nc + " db guc-set spock.allow_ddl_from_functions on;"
        
            message = f"Setup spock"
            run_cmd(cmd, n, message=message, verbose=verbose)
        
        if db_settings["auto_ddl"] == "on":
            util.message("#")
    return 0


def remove(cluster_name, force=False):
    """Remove a test cluster.
    
    Remove a cluster. This will remove spock subscriptions and nodes, and
    then stop postgres on each node. If the flag force is set to true, 
    then it will also remove the pgedge directory on each node.
    This command requires a JSON file with the same name as the cluster to
    be in the cluster/<cluster_name>. 
    
    Example: cluster remove demo 
    :param cluster_name: The name of the cluster. 
    """
    db, db_settings, nodes = load_json(cluster_name)

    ssh_un_cross_wire(
        cluster_name, db[0]["db_name"], db_settings, db[0]["db_user"],
        db[0]["db_password"], nodes
    )

    util.message("\n## Ensure that PG is stopped.")
    for nd in nodes:
        cmd = f"{nd['path']}{os.sep}pgedge stop 2> {os.sep}dev{os.sep}null"
        util.echo_cmd(cmd, host=nd["public_ip"], usr=nd["os_user"],
                      key=nd["ssh_key"])
    if force == True:
        for nd in nodes:
            util.message("\n## Ensure that pgEdge root directory is gone")
            cmd = f"rm -rf {nd['path']}{os.sep}pgedge"
            util.echo_cmd(cmd, host=nd["public_ip"], usr=nd["os_user"],
                          key=nd["ssh_key"])


def add_db(cluster_name, database_name, username, password):
    """Add a database to an existing pgEdge cluster.
    
       Create the new database in the cluster, install spock, and create all spock nodes and subscriptions.
       This command requires a JSON file with the same name as the cluster to be in the cluster/<cluster_name>. \n
       Example: cluster add-db demo test admin password
       :param cluster_name: The name of the existing cluster.
       :param database_name: The name of the new database.
       :param username: The name of the user that will be created and own the db. 
       :param password: The password for the new user.
    """
    util.message(f"## Loading cluster '{cluster_name}' json definition file")
    db, db_settings, nodes = load_json(cluster_name)

    verbose = db_settings.get("log_level", "none")

    db_json = {}
    db_json["username"] = username
    db_json["password"] = password
    db_json["name"] = database_name

    util.message(f"## Creating database {database_name}")
    create_spock_db(nodes,db_json, db_settings)
    ssh_cross_wire_pgedge(cluster_name, database_name, db_settings, username, password, nodes, verbose)
    util.message(f"## Updating cluster '{cluster_name}' json definition file")
    update_json(cluster_name, db_json)

import os
import json
import datetime
import getpass
from ipaddress import ip_address

def json_create(cluster_name, num_nodes, db, usr, passwd, pg=None, port=None):
    """
    Create a Cluster Configuration JSON file with validations for HA, BackRest, and Spock.

    This function creates a JSON configuration file that can be used to define a cluster.
    Example: ./pgedge cluster json-create test_cluster 3 mydb myuser mypass

    Args:
        cluster_name (str): The name of the cluster. A directory with this same name will be created in the cluster directory, and the JSON file will have the same name.
        num_nodes (int): The number of main nodes in the cluster.
        db (str): The database name.
        usr (str): The username of the superuser created for this database.
        passwd (str): The password for the above user.
        pg (str, optional): The PostgreSQL version of the database. If not provided, the user will be prompted. Defaults to 17.
        port (int, optional): The starting port number for the database. Defaults to 5432 if not provided.
    """

    # Validate parameters
    if not isinstance(cluster_name, str) or not cluster_name:
        raise ValueError("Invalid cluster name. It must be a non-empty string.")
    if not isinstance(num_nodes, int) or num_nodes <= 0:
        raise ValueError("Invalid number of nodes. It must be a positive integer.")
    if not isinstance(db, str) or not db:
        raise ValueError("Invalid database name. It must be a non-empty string.")
    if not isinstance(usr, str) or not usr:
        raise ValueError("Invalid username. It must be a non-empty string.")
    if not isinstance(passwd, str) or not passwd:
        raise ValueError("Invalid password. It must be a non-empty string.")
    if pg and (not isinstance(pg, str) or pg not in ['16', '17']):
        raise ValueError("Invalid PostgreSQL version. Allowed versions are '16' and '17'.")
    if port and (not isinstance(port, int) or port < 1 or port > 65535):
        raise ValueError("Invalid port number. It must be an integer between 1 and 65535.")

    # Function to get cluster directory and file paths
    def get_cluster_info(cluster_name):
        cluster_dir = os.path.join(os.getcwd(), "cluster", cluster_name)
        cluster_file = os.path.join(cluster_dir, f"{cluster_name}.json")
        return cluster_dir, cluster_file

    # Function to exit with a message
    class Util:
        @staticmethod
        def exit_message(message, code=1):
            print(f"✘ {message}")
            exit(code)

    util = Util()

    # Get cluster directory and file paths
    cluster_dir, cluster_file = get_cluster_info(cluster_name)

    os.makedirs(cluster_dir, exist_ok=True)

    cluster_json = {
        "json_version": "1.1",
        "cluster_name": cluster_name,
        "log_level": "debug",
        "update_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S GMT")
    }

    # Prompt for PostgreSQL version if not provided
    while True:
        if not pg:
            pg_input = input("PostgreSQL version (16 or 17) [default: 17]: ").strip() or "17"
        else:
            pg_input = str(pg).strip()

        if pg_input in ['16', '17']:
            pg_version_int = int(pg_input)
            break
        else:
            print("Invalid PostgreSQL version. Allowed versions are 16 and 17.")

    pgedge_json = {
        "pg_version": str(pg_version_int),
        "auto_start": "off"
    }

    # Prompt for Spock version
    while True:
        spock_version = input("Spock version (e.g., 4.0.5) or press Enter for 'default': ").strip()
        if not spock_version:
            spock_version = "default"
            break

        version_parts = spock_version.split('.')
        if len(version_parts) == 3 and all(part.isdigit() for part in version_parts):
            break
        else:
            print("Invalid Spock version format. Expected format: X.Y.Z")

    spock_json = {
        "spock_version": spock_version,
        "auto_ddl": "off"
    }
    pgedge_json["spock"] = spock_json

    database_json = [{
        "db_name": db,
        "db_user": usr,
        "db_password": passwd
    }]
    pgedge_json["databases"] = database_json

    cluster_json["pgedge"] = pgedge_json

    # Ask if this is an HA Cluster
    ha_cluster_input = input("Is this an HA Cluster? (Y/N): ").strip().lower()
    is_ha_cluster = ha_cluster_input in ['y', 'yes']

    # Ask if BackRest should be enabled
    backrest_enabled_input = input("Do you want to enable BackRest for this cluster? (Y/N): ").strip().lower()
    backrest_enabled = backrest_enabled_input in ['y', 'yes']

    # Initialize backrest_json based on user input
    if backrest_enabled:
        backrest_storage_path = input("   pgBackRest storage path (default: /var/lib/pgbackrest): ").strip() or "/var/lib/pgbackrest"
        backrest_archive_mode = input("   pgBackRest archive mode (on/off) (default: on): ").strip().lower() or "on"
        if backrest_archive_mode not in ['on', 'off']:
            util.exit_message("Invalid BackRest archive mode. Allowed values are 'on' or 'off'.")

        backrest_json = {
            "stanza": "demo_stanza",
            "repo1-path": backrest_storage_path,
            "repo1-retention-full": "7",
            "log-level-console": "info",
            "repo1-cipher-type": "aes-256-cbc",
            "archive_mode": backrest_archive_mode
        }
    else:
        backrest_json = None

    node_groups = []
    os_user = getpass.getuser()
    default_ip = "127.0.0.1"
    default_port = port if port else 5432

    current_replica_port = 6432  # Starting port for replica nodes

    for n in range(1, num_nodes + 1):
        print(f"Configuring Node {n}")
        node_json = {
            "ssh": {"os_user": os_user, "private_key": ""},
            "name": f"n{n}",
            "is_active": "on"
        }

        node_ip = input(f"  IP address for Node {n} (leave blank for default '{default_ip}'): ").strip() or default_ip
        node_json["public_ip"] = node_ip
        node_json["private_ip"] = node_ip

        node_default_port = default_port + n - 1
        node_port_input = input(f"  PostgreSQL port for Node {n} (leave blank for default '{node_default_port}'): ").strip()
        if not node_port_input:
            node_port = node_default_port
        else:
            try:
                node_port = int(node_port_input)
                if node_port < 1 or node_port > 65535:
                    print("  Invalid port number. Using default port.")
                    node_port = node_default_port
            except ValueError:
                print("  Invalid port input. Using default port.")
                node_port = node_default_port
        node_json["port"] = str(node_port)

        node_json["path"] = f"/home/{os_user}/{cluster_name}/n{n}"
        if backrest_enabled:
            node_json["backrest"] = backrest_json

        if is_ha_cluster:
            while True:
                try:
                    replicas_for_node_input = input(f"  Number of replica nodes for Node {n}: ").strip()
                    replicas_for_node = int(replicas_for_node_input)
                    if replicas_for_node < 0:
                        print("  Number of replicas cannot be negative. Please enter 0 or a positive integer.")
                        continue
                    break
                except ValueError:
                    print("  Invalid input. Please enter a numeric value.")
                    continue
        else:
            replicas_for_node = 0

        node_json["replicas"] = replicas_for_node

        if replicas_for_node > 0:
            for i in range(1, replicas_for_node + 1):
                print(f"\n  Configuring Replica Node {i} for Node {n}:")
                sub_node_json = {
                    "ssh": {"os_user": os_user, "private_key": ""},
                    "name": f"{node_json['name']}_ro_{i}",
                    "is_active": "off"
                }

                replica_ip = input(f"    IP address of replica Node {i} (leave blank for default '{default_ip}'): ").strip() or default_ip
                sub_node_json["public_ip"] = replica_ip
                sub_node_json["private_ip"] = replica_ip

                replica_port_input = input(f"    PostgreSQL port of replica Node {i} (leave blank for default '{current_replica_port}'): ").strip()
                if not replica_port_input:
                    replica_port = current_replica_port
                else:
                    try:
                        replica_port = int(replica_port_input)
                        if replica_port < 1 or replica_port > 65535:
                            print("    Invalid port number. Using default port.")
                            replica_port = current_replica_port
                    except ValueError:
                        print("    Invalid port input. Using default port.")
                        replica_port = current_replica_port
                sub_node_json["port"] = str(replica_port)
                sub_node_json["path"] = f"/home/{os_user}/{cluster_name}/{sub_node_json['name']}"
                if backrest_enabled:
                    sub_node_json["backrest"] = backrest_json

                node_json.setdefault("sub_nodes", []).append(sub_node_json)
                current_replica_port += 1

        node_groups.append(node_json)

    cluster_json["node_groups"] = node_groups

    validation_errors = []

    for node in node_groups:
        if not node.get("name"):
            validation_errors.append("Node name is missing.")
        if not node.get("port"):
            validation_errors.append(f"Port is missing for node {node.get('name')}.")
        else:
            try:
                port_int = int(node["port"])
                if port_int < 1 or port_int > 65535:
                    validation_errors.append(f"Invalid port number {port_int} for node {node.get('name')}.")
            except ValueError:
                validation_errors.append(f"Port must be a valid number for node {node.get('name')}.")
        
        public_ip = node.get("public_ip", "")
        private_ip = node.get("private_ip", "")
        if not public_ip and not private_ip:
            validation_errors.append(f"Either public_ip or private_ip must be provided for node {node.get('name')}.")
        try:
            if public_ip:
                ip_address(public_ip)
            if private_ip:
                ip_address(private_ip)
        except ValueError:
            validation_errors.append(f"Invalid IP address provided for node {node.get('name')}.")
        
        for sub_node in node.get("sub_nodes", []):
            if not sub_node.get("name"):
                validation_errors.append("Sub-node name is missing.")
            if not sub_node.get("port"):
                validation_errors.append(f"Port is missing for sub-node {sub_node.get('name')}.")
            else:
                try:
                    port_int = int(sub_node["port"])
                    if port_int < 1 or port_int > 65535:
                        validation_errors.append(f"Invalid port number {port_int} for sub-node {sub_node.get('name')}.")
                except ValueError:
                    validation_errors.append(f"Port must be a valid number for sub-node {sub_node.get('name')}.")
            
            public_ip = sub_node.get("public_ip", "")
            private_ip = sub_node.get("private_ip", "")
            if not public_ip and not private_ip:
                validation_errors.append(f"Either public_ip or private_ip must be provided for sub-node {sub_node.get('name')}.")
            try:
                if public_ip:
                    ip_address(public_ip)
                if private_ip:
                    ip_address(private_ip)
            except ValueError:
                validation_errors.append(f"Invalid IP address provided for sub-node {sub_node.get('name')}.")
    if validation_errors:
        print("\nValidation Errors:")
        for error in validation_errors:
            print(f" - {error}")
        util.exit_message("Configuration validation failed. Please correct the errors and try again.")

    bold_start = "\033[1m"
    bold_end = "\033[0m"

    print("\n" + "#" * 80)
    print(f"#     {bold_start}Version{bold_end}        : pgEdge 24.10-5 (Constellation)")
    print(f"# {bold_start}User & Host{bold_end}        : {os_user}    {os.getcwd()}")
    print(f"#          {bold_start}OS{bold_end}        : Rocky Linux9.4 (Blue Onyx), glibc-2.34, Python 3.9.18 ()")
    print(f"#     {bold_start}Machine{bold_end}        : 7 GB")
    print(f"#    {bold_start}Repo URL{bold_end}        : http://localhost:8000")
    print(f"# {bold_start}Last Update{bold_end}        : None")
    print(f"# {bold_start}Cluster Name{bold_end}       : {cluster_name}")
    print(f"# {bold_start}PostgreSQL Version{bold_end} : {pg_version_int}")
    print(f"# {bold_start}Spock Version{bold_end}      : {spock_version}")
    print(f"# {bold_start}HA Cluster{bold_end}         : {'Yes' if is_ha_cluster else 'No'}")
    print(f"# {bold_start}BackRest Enabled{bold_end}   : {'Yes' if backrest_enabled else 'No'}")
    print("#" * 80)

    confirm_save = input("Do you want to save this configuration? (Y/N): ").strip().lower()
    if confirm_save not in ['yes', 'y']:
        util.exit_message("Configuration not saved.")

    try:
        with open(cluster_file, "w") as text_file:
            text_file.write(json.dumps(cluster_json, indent=2))
        print(f"\nCluster configuration saved to {cluster_file}")
    except Exception as e:
        util.exit_message(f"Unable to create JSON file: {e}", 1)

def create_spock_db(nodes,db,db_settings):
    for n in nodes:
        ip = n["public_ip"] if "public_ip" in n else n["private_ip"]
        nc = n["path"] + os.sep + "pgedge" + os.sep + "pgedge "
        cmd = nc + " db create -U " + db["username"] + " -d " + db["name"] + " -p " + db["password"]
        util.echo_cmd(cmd, host=ip, usr=n["os_user"], key=n["ssh_key"])
        if db_settings["auto_ddl"] == "on":
            cmd = nc + " db guc-set spock.enable_ddl_replication on;"
            cmd = cmd + " " + nc + " db guc-set spock.include_ddl_repset on;"
            cmd = cmd + " " + nc + " db guc-set spock.allow_ddl_from_functions on;"
            util.echo_cmd(cmd, host=ip, usr=n["os_user"], key=n["ssh_key"])


def update_json(cluster_name, db_json):
    """Update the cluster JSON configuration with new database information."""
    parsed_json = get_cluster_json(cluster_name)

    cluster_dir, cluster_file = get_cluster_info(cluster_name)

    os.system(f"mkdir -p {cluster_dir}{os.sep}backup")
    timeof = datetime.datetime.now().strftime('%y%m%d_%H%M')
    os.system(f"cp {cluster_dir}{os.sep}{cluster_name}.json {cluster_dir}{os.sep}backup/{cluster_name}_{timeof}.json")
    text_file = open(cluster_dir + os.sep + cluster_name + ".json", "w")
    parsed_json["database"]["databases"].append(db_json)
    try:
        text_file.write(json.dumps(parsed_json, indent=2))
        text_file.close()
    except Exception:
        util.exit_message("Unable to update JSON file", 1)


def init(cluster_name, install=True):
    """
    Initialize a cluster via Cluster Configuration JSON file.

    Install pgEdge on each node, create the initial database, install Spock,
    and create all Spock nodes and subscriptions. Additional databases will
    be created with all Spock nodes and subscriptions if defined in the JSON
    file. This command requires a JSON file with the same name as the cluster
    to be in the cluster/<cluster_name>.

    Args:
        cluster_name (str): The name of the cluster.
        install (bool): True by default, 
    """
    util.message(f"## Loading cluster '{cluster_name}' json definition file")
    db, db_settings, nodes = load_json(cluster_name)
    parsed_json = get_cluster_json(cluster_name)
   
    if parsed_json.get("log_level"):
       verbose = parsed_json["log_level"]
    else:
       verbose = "none"

    for nd in nodes:
        message = f"Checking ssh on {nd['public_ip']}"
        run_cmd(cmd="hostname", node=nd, message=message, verbose=verbose)

    ssh_install_pgedge(
        cluster_name, db[0]["db_name"], db_settings, db[0]["db_user"],
        db[0]["db_password"], nodes, install, verbose
    )
    ssh_cross_wire_pgedge(
        cluster_name, db[0]["db_name"], db_settings, db[0]["db_user"],
        db[0]["db_password"], nodes, verbose
    )

    if len(db) > 1:
        for database in db[1:]:
            create_spock_db(nodes, database, db_settings)
            ssh_cross_wire_pgedge(
                cluster_name, database["db_name"], db_settings, database["db_user"],
                database["db_password"], nodes, verbose
            )

    pg_ver = db_settings["pg_version"]
    for node in nodes:
        if "sub_nodes" in node:
            for n in node["sub_nodes"]:
                ssh_install(
                    cluster_name, db[0]["db_name"], db_settings, db[0]["db_user"],
                    db[0]["db_password"], n, install
                )
                ssh_setup(
                    cluster_name, db[0]["db_name"], db_settings, db[0]["db_user"],
                    db[0]["db_password"], n, install
                )
                manage_node(n, "stop", f"pg{pg_ver}", verbose)

                pgdata = f"{node['path']}/pgedge/data/pg{pg_ver}"
                cmd = f"rm -rf {pgdata}"
                message = f"Removing old data directory"
                run_cmd(cmd, n, message=message, verbose=verbose)
            
            sub_nodes = node["sub_nodes"]
        
            etcd.configure_etcd(node, sub_nodes)
            ha_patroni.configure_patroni(node, sub_nodes, db[0], db_settings)


def add_node(cluster_name, source_node, target_node, repo1_path=None, backup_id=None, script=" ", stanza=" ", install=True):
    """
    Adds a new node to a cluster, copying configurations from a specified 
    source node.

    Args:
        cluster_name (str): The name of the cluster to which the node is being 
                            added.
        source_node (str): The node from which configurations are copied.
        target_node (str): The new node. 
        repo1_path (str): The repo1 path to use.
        backup_id (str): Backup ID.
        stanza (str): Stanza name.
        script (str): Bash script.
    """
    if (repo1_path and not backup_id) or (backup_id and not repo1_path):
        util.exit_message("Both repo1_path and backup_id must be supplied together.")
    
    json_validate(cluster_name)
    db, db_settings, nodes = load_json(cluster_name)

    cluster_data = get_cluster_json(cluster_name)
    if cluster_data is None:
        util.exit_message("Cluster data is missing.")
    pg = db_settings["pg_version"]
    pgV = f"pg{pg}"
    verbose = cluster_data.get("log_level", "info")

    # Load and validate the target node JSON
    target_node_file = f"{target_node}.json"
    if not os.path.isfile(target_node_file):
        util.exit_message(f"New node json file '{target_node_file}' not found")

    try:
        with open(target_node_file, "r") as f:
            target_node_data = json.load(f)
            json_validate_add_node(target_node_data)
    except Exception as e:
        util.exit_message(
            f"Unable to load new node jsaon def file '{target_file_name}\n{e}")

    # Retrieve source node data
    source_node_data = next((node for node in nodes if node["name"] == source_node), None)
    if source_node_data is None:
        util.exit_message(f"Source node '{source_node}' not found in cluster data.")

    for group in target_node_data.get("node_groups", []):
        ssh_info = group.get("ssh")
        os_user = ssh_info.get("os_user", "")
        ssh_key = ssh_info.get("private_key", "")

        new_node_data = {
            "ssh": ssh_info,
            "name": group.get("name", ""),
            "is_active": group.get("is_active", ""),
            "public_ip": group.get("public_ip", ""),
            "private_ip": group.get("private_ip", ""),
            "port": group.get("port", ""),
            "path": group.get("path", ""),
            "os_user": os_user,
            "ssh_key": ssh_key
        }

    if "public_ip" not in new_node_data and "private_ip" not in new_node_data:
        util.exit_message("Both public_ip and private_ip are missing in target node data.")
    
    if "public_ip" in source_node_data and "private_ip" in source_node_data:
        source_node_data["ip_address"] = source_node_data["public_ip"]
    else:
        source_node_data["ip_address"] = source_node_data.get("public_ip", source_node_data.get("private_ip"))
    
    if "public_ip" in new_node_data and "private_ip" in new_node_data:
        new_node_data["ip_address"] = new_node_data["public_ip"]
    else:
        new_node_data["ip_address"] = new_node_data.get("public_ip", new_node_data.get("private_ip"))
    
    # Fetch backrest settings from cluster JSON
    backrest_settings = cluster_data.get("backrest", {})
    stanza = backrest_settings.get("stanza", f"pg{pg}")
    repo1_retention_full = backrest_settings.get("repo1-retention-full", "7")
    log_level_console = backrest_settings.get("log-level-console", "info")
    repo1_cipher_type = backrest_settings.get("repo1-cipher-type", "aes-256-cbc")


    rc = ssh_install_pgedge(cluster_name, db[0]["db_name"], db_settings, db[0]["db_user"],
                            db[0]["db_password"], [new_node_data], install, verbose)

    os_user = new_node_data["os_user"]
    repo1_type = new_node_data.get("repo1_type", "posix")
    port = source_node_data["port"]
    pg1_path = f"{source_node_data['path']}/pgedge/data/pg{pg}"

    if not repo1_path:
        cmd = f"{source_node_data['path']}/pgedge/pgedge install backrest"
        message = f"Installing backrest"
        run_cmd(cmd, source_node_data, message=message, verbose=verbose)

        repo1_path = f"/var/lib/pgbackrest/{source_node_data['name']}"
        cmd = f"sudo rm -rf {repo1_path}"
        message = f"Removing the repo-path"
        run_cmd(cmd, source_node_data, message=message, verbose=verbose)

        args = (f'--repo1-path {repo1_path} --stanza {stanza} '
                f'--pg1-path {pg1_path} --repo1-type {repo1_type} '
                f'--log-level-console {log_level_console} --pg1-port {port} '
                f'--db-socket-path /tmp --repo1-cipher-type {repo1_cipher_type}')

        cmd = f"{source_node_data['path']}/pgedge/pgedge backrest command stanza-create '{args}'"
        message = f"Creating stanza {stanza}"
        run_cmd(cmd, source_node_data, message=message, verbose=verbose)

        cmd = (f"{source_node_data['path']}/pgedge/pgedge backrest set_postgresqlconf {stanza} "
               f"{pg1_path} {repo1_path} {repo1_type}")
        message = f"Modifying postgresql.conf file"
        run_cmd(cmd, source_node_data, message=message, verbose=verbose)

        cmd = f"{source_node_data['path']}/pgedge/pgedge backrest set_hbaconf"
        message = f"Modifying pg_hba.conf file"
        run_cmd(cmd, source_node_data, message=message, verbose=verbose)

        sql_cmd = "select pg_reload_conf()"
        cmd = f"{source_node_data['path']}/pgedge/pgedge psql '{sql_cmd}' {db[0]['db_name']}"
        message = f"Reload configuration pg_reload_conf()"
        run_cmd(cmd, source_node_data, message=message, verbose=verbose)

        args = args + f' --repo1-retention-full={repo1_retention_full} --type=full'
        cmd = f"{source_node_data['path']}/pgedge/pgedge backrest command backup '{args}'"
        message = f"Creating full backup"
        run_cmd(cmd, source_node_data, message=message, verbose=verbose)
    else:
        cmd = (f"{source_node_data['path']}/pgedge/pgedge backrest set_postgresqlconf {stanza} "
               f"{pg1_path} {repo1_path} {repo1_type}")
        message = f"Modifying postgresql.conf file"
        run_cmd(cmd, source_node_data, message=message, verbose=verbose)

        cmd = f"{source_node_data['path']}/pgedge/pgedge backrest set_hbaconf"
        message = f"Modifying pg_hba.conf file"
        run_cmd(cmd, source_node_data, message=message, verbose=verbose)

        sql_cmd = "select pg_reload_conf()"
        cmd = f"{source_node_data['path']}/pgedge/pgedge psql '{sql_cmd}' {db[0]['db_name']}"
        message = f"Reload configuration pg_reload_conf()"
        run_cmd(cmd, source_node_data, message=message, verbose=verbose)

        repo1_type = new_node_data.get("repo1_type", "posix")
        if repo1_type == "s3":
            for env_var in ["PGBACKREST_REPO1_S3_KEY", "PGBACKREST_REPO1_S3_BUCKET", 
                            "PGBACKREST_REPO1_S3_KEY_SECRET", "PGBACKREST_REPO1_CIPHER_PASS"]:
                if env_var not in os.environ:
                    util.exit_message(f"Environment variable {env_var} not set.")
            s3_export_cmds = [f'export {env_var}={os.environ[env_var]}' for env_var in [
                "PGBACKREST_REPO1_S3_KEY", "PGBACKREST_REPO1_S3_BUCKET", 
                "PGBACKREST_REPO1_S3_KEY_SECRET", "PGBACKREST_REPO1_CIPHER_PASS"]]
            run_cmd(" && ".join(s3_export_cmds), source_node_data, message="Setting S3 environment variables on source node", verbose=verbose)
            run_cmd(" && ".join(s3_export_cmds), new_node_data, message="Setting S3 environment variables on target node", verbose=verbose)

    cmd = f"{new_node_data['path']}/pgedge/pgedge install backrest"
    message = f"Installing backrest"
    run_cmd(cmd, new_node_data, message=message, verbose=verbose)

    manage_node(new_node_data, "stop", f"pg{pg}", verbose)
    cmd = f'rm -rf {new_node_data["path"]}/pgedge/data/pg{pg}'
    message = f"Removing old data directory"
    run_cmd(cmd, new_node_data, message=message, verbose=verbose)

    args = (f'--repo1-path {repo1_path} --repo1-cipher-type {repo1_cipher_type} ')

    if backup_id:
        args += f'--set={backup_id} '

    cmd = (f'{new_node_data["path"]}/pgedge/pgedge backrest command restore '
           f'--repo1-type={repo1_type} --stanza={stanza} '
           f'--pg1-path={new_node_data["path"]}/pgedge/data/pg{pg} {args}')

    message = f"Restoring backup"
    run_cmd(cmd, new_node_data, message=message, verbose=verbose)
    

    pgd = f'{new_node_data["path"]}/pgedge/data/pg{pg}'
    pgc = f'{pgd}/postgresql.conf'

    cmd = f'echo "ssl_cert_file=\'{pgd}/server.crt\'" >> {pgc}'
    message = f"Setting ssl_cert_file"
    run_cmd(cmd, new_node_data, message=message, verbose=verbose)

    cmd = f'echo "ssl_key_file=\'{pgd}/server.key\'" >> {pgc}'
    message = f"Setting ssl_key_file"
    run_cmd(cmd, new_node_data, message=message, verbose=verbose)

    cmd = f'echo "log_directory=\'{pgd}/log\'" >> {pgc}'
    message = f"Setting log_directory"
    run_cmd(cmd, new_node_data, message=message, verbose=verbose)

    cmd = (f'echo "shared_preload_libraries = '
           f'\'pg_stat_statements, snowflake, spock\'" >> {pgc}')
    message = f"Setting shared_preload_libraries"
    run_cmd(cmd, new_node_data, message=message, verbose=verbose)
    

    cmd = (f'{new_node_data["path"]}/pgedge/pgedge backrest configure_replica {stanza} '
           f'{new_node_data["path"]}/pgedge/data/pg{pg} {source_node_data["ip_address"]} '
           f'{source_node_data["port"]} {source_node_data["os_user"]}')
    message = f"Configuring PITR on replica"
    run_cmd(cmd, new_node_data, message=message, verbose=verbose)

    if script.strip() and os.path.isfile(script):
        util.echo_cmd(f'{script}')

    terminate_cluster_transactions(nodes, db[0]['db_name'], f"pg{pg}", verbose)

    spock = db_settings["spock_version"]
    v4 = False
    spock_maj = 3
    if spock:
        ver = [int(x) for x in spock.split('.')]
        spock_maj = ver[0]
        spock_min = ver[1]
        if spock_maj >= 4:
            v4 = True

    set_cluster_readonly(nodes, True, db[0]['db_name'], f"pg{pg}", v4, verbose)
    
    
    manage_node(new_node_data, "start", f"pg{pg}", verbose)
    time.sleep(5)

    check_cluster_lag(new_node_data, db[0]['db_name'], f"pg{pg}", verbose)

    sql_cmd = "SELECT pg_promote()"
    cmd = f"{new_node_data['path']}/pgedge/pgedge psql '{sql_cmd}' {db[0]['db_name']}"
    message = f"Promoting standby to primary"
    run_cmd(cmd, new_node_data, message=message, verbose=verbose)

    sql_cmd = "DROP extension spock cascade"
    cmd = f"{new_node_data['path']}/pgedge/pgedge psql '{sql_cmd}' {db[0]['db_name']}"
    message = f"DROP extension spock cascade"
    run_cmd(cmd, new_node_data, message=message, verbose=verbose)

    parms = f"spock{spock_maj}{spock_min}" if spock else "spock"

    cmd = (f'cd {new_node_data["path"]}/pgedge/; ./pgedge install {parms}')
    message = f"Re-installing spock"
    run_cmd(cmd, new_node_data, message=message, verbose=verbose)

    sql_cmd = "CREATE EXTENSION spock"
    cmd = f"{new_node_data['path']}/pgedge/pgedge psql '{sql_cmd}' {db[0]['db_name']}"
    message = f"Create extension spock"
    run_cmd(cmd, new_node_data, message=message, verbose=verbose)

    create_node(new_node_data, db[0]['db_name'], verbose)

    if not v4:
        set_cluster_readonly(nodes, False, db[0]['db_name'], f"pg{pg}", v4, verbose)

    create_sub(nodes, new_node_data, db[0]['db_name'], verbose)
    create_sub_new(nodes, new_node_data, db[0]['db_name'], verbose)

    if v4:
        set_cluster_readonly(nodes, False, db[0]['db_name'], f"pg{pg}", v4, verbose)

    cmd = (f'cd {new_node_data["path"]}/pgedge/; ./pgedge spock node-list {db[0]["db_name"]}')
    message = f"Listing spock nodes"
    result = run_cmd(cmd, node=new_node_data, message=message, verbose=verbose,
                     capture_output=True)
    print(f"\n{result.stdout}")

    sql_cmd = "select node_id,node_name from spock.node"
    cmd = f"{source_node_data['path']}/pgedge/pgedge psql '{sql_cmd}' {db[0]['db_name']}"
    message = f"List nodes"
    result = run_cmd(cmd, node=source_node_data, message=message, verbose=verbose,
                     capture_output=True)
    print(f"\n{result.stdout}")

    for node in nodes:
        sql_cmd = ("select sub_id,sub_name,sub_enabled,sub_slot_name,"
                   "sub_replication_sets from spock.subscription")
        cmd = f"{node['path']}/pgedge/pgedge psql '{sql_cmd}' {db[0]['db_name']}"
        message = f"List subscriptions"
        result = run_cmd(cmd, node=node, message=message, verbose=verbose,
                         capture_output=True)
        print(f"\n{result.stdout}")

    sql_cmd = ("select sub_id,sub_name,sub_enabled,sub_slot_name,"
               "sub_replication_sets from spock.subscription")
    cmd = f"{new_node_data['path']}/pgedge/pgedge psql '{sql_cmd}' {db[0]['db_name']}"
    message = f"List subscriptions"
    result = run_cmd(cmd, node=new_node_data, message=message, verbose=verbose,
                     capture_output=True)
    print(f"\n{result.stdout}")

    # Remove unnecessary keys before appending new node to the cluster data
    new_node_data.pop('repo1_type', None)
    new_node_data.pop('os_user', None)
    new_node_data.pop('ssh_key', None)

    # Append new node data to the cluster JSON
    node_group = target_node_data.get
    cluster_data["node_groups"].append(new_node_data)
    cluster_data["update_date"] = datetime.datetime.now().astimezone().isoformat()

    write_cluster_json(cluster_name, cluster_data)

def json_validate_add_node(data):
    """Validate the structure of a node configuration JSON file."""
    required_keys = ["json_version", "node_groups"]
    node_group_keys = ["ssh", "name", "is_active", "public_ip", "private_ip", "port", "path"]
    ssh_keys = ["os_user", "private_key"]
    
    if "json_version" not in data or data["json_version"] == "1.0":
        util.exit_message("Invalid or missing JSON version.")

    for key in required_keys:
        if key not in data:
            util.exit_message(f"Key '{key}' missing from JSON data.")

    for group in data["node_groups"]:
        for node_group_key in node_group_keys:
            if node_group_key not in group:
                util.exit_message(f"Key '{node_group_key}' missing from node group.")

        ssh_info = group.get("ssh", {})
        for ssh_key in ssh_keys:
            if ssh_key not in ssh_info:
                util.exit_message(f"Key '{ssh_key}' missing from ssh configuration.")

                
        if "public_ip" not in group and "private_ip" not in group:
            util.exit_message("Both 'public_ip' and 'private_ip' are missing from node group.")

    util.message(f"New node json file structure is valid.", "success")

def remove_node(cluster_name, node_name):
    """Remove a node from the cluster configuration."""
    json_validate(cluster_name)
    db, db_settings, nodes = load_json(cluster_name)
    cluster_data = get_cluster_json(cluster_name)
    if cluster_data is None:
        util.exit_message("Cluster data is missing.")

    pg = db_settings["pg_version"]
    pgV = f"pg{pg}"

    db, db_settings, nodes = load_json(cluster_name)
    dbname = db[0]["db_name"]
    verbose = cluster_data.get("log_level", "info")

    for node in nodes:
        os_user = node["os_user"]
        ssh_key = node["ssh_key"]
        message = f"Checking ssh on {node['public_ip']}"
        cmd = "hostname"
        run_cmd(cmd, node, message=message, verbose=verbose)

    for node in nodes:
        if node.get('name') != node_name:
            sub_name = f"sub_{node['name']}{node_name}"
            cmd = (f"cd {node['path']}/pgedge/; "
                   f"./pgedge spock sub-drop {sub_name} {dbname}")
            message = f"Dropping subscriptions {sub_name}"
            run_cmd(cmd, node, message=message, verbose=verbose, ignore=True)

    sub_names = []
    for node in nodes:
        if node.get('name') != node_name:
            sub_name = f"sub_{node_name}{node['name']}"
            sub_names.append(sub_name)

    for node in nodes:
        if node.get('name') == node_name:
            for sub_name in sub_names:
                cmd = (f"cd {node['path']}/pgedge/; "
                       f"./pgedge spock sub-drop {sub_name} {dbname}")
                message = f"Dropping subscription {sub_name}"
                run_cmd(cmd, node, message=message, verbose=verbose, ignore=True)
            
            cmd = (f"cd {node['path']}/pgedge/; "
                   f"./pgedge spock node-drop {node['name']} {dbname}")
            message = f"Dropping node {node['name']}"
            run_cmd(cmd, node, message=message, verbose=verbose, ignore=True)

    for node in nodes:
        if node.get('name') == node_name:
            manage_node(node, "stop", pgV, verbose)
        else:
            cmd = (f'cd {node["path"]}/pgedge/; ./pgedge spock node-list {dbname}')
            message = f"Listing spock nodes"
            result = run_cmd(cmd, node=node, message=message, verbose=verbose,
                             capture_output=True)
            print(f"\n{result.stdout}")

    empty_groups = []
    for group in cluster_data["node_groups"]:
        if group["name"] == node_name:
            cluster_data["node_groups"].remove(group)
            continue
        for node in group.get("sub_nodes", []):
            if node["name"] == node_name:
                group["sub_nodes"].remove(node)
        if not group.get("sub_nodes") and group["name"] == node_name:
            empty_groups.append(group)

    # Remove empty connection groups
    for group in empty_groups:
        cluster_data["node_groups"].remove(group)

    write_cluster_json(cluster_name, cluster_data)



def manage_node(node, action, pgV, verbose):
    """
    Starts or stops a cluster based on the provided action.
    """
    if action not in ['start', 'stop']:
        raise ValueError("Invalid action. Use 'start' or 'stop'.")

    action_message = "Starting" if action == 'start' else "Stopping"

    if action == 'start':
        cmd = (f"cd {node['path']}/pgedge/; "
               f"./pgedge config {pgV} --port={node['port']}; "
               f"./pgedge start;")
    else:
        cmd = (f"cd {node['path']}/pgedge/; "
               f"./pgedge stop")

    message=f"{action_message} new node"
    run_cmd(cmd, node, message=message, verbose=verbose)

def create_node(node, dbname, verbose):
    """
    Creates a new node in the database cluster.
    """
    ndip = node["private_ip"] if node["private_ip"] else node["public_ip"]
    cmd = (f"cd {node['path']}/pgedge/; "
           f"./pgedge spock node-create {node['name']} "
           f"'host={ndip} user=pgedge dbname={dbname} "
           f"port={node['port']}' {dbname}")
    message=f"Creating new node {node['name']}"
    run_cmd(cmd, node, message=message, verbose=verbose)

def create_sub_new(nodes, n, dbname, verbose):
    """
    Creates subscriptions for each node to a new node in the cluster.
    """
    for node in nodes:
        sub_name = f"sub_{n['name']}{node['name']}"
        ndip = node["private_ip"] if node["private_ip"] else node["public_ip"]
        cmd = (f"cd {n['path']}/pgedge/; "
               f"./pgedge spock sub-create {sub_name} "
               f"'host={ndip} user=pgedge dbname={dbname} "
               f"port={node['port']}' {dbname}")
        message=f"Creating new subscriptions {sub_name}"
        run_cmd(cmd = cmd, node=n, message=message, verbose=verbose)

def create_sub(nodes, new_node, dbname, verbose):
    """
    Creates subscriptions for each node to a new node in the cluster.
    """
    for n in nodes:
        sub_name = f"sub_{n['name']}{new_node['name']}"
        ndip = new_node["private_ip"] if new_node["private_ip"] else new_node["public_ip"]
        cmd = (f"cd {n['path']}/pgedge/; "
               f"./pgedge spock sub-create {sub_name} "
               f"'host={ndip} user=pgedge dbname={dbname} "
               f"port={new_node['port']}' {dbname}")
        message=f"Creating subscriptions {sub_name}"
        run_cmd(cmd = cmd, node=n, message=message, verbose=verbose)

def terminate_cluster_transactions(nodes, dbname, stanza, verbose):
    sql_cmd = "SELECT spock.terminate_active_transactions()"
    for node in nodes:
        cmd = f"{node['path']}/pgedge/pgedge psql '{sql_cmd}' {dbname}"
        message = f"Terminating·cluster·transactions"
        result = run_cmd(cmd = cmd, node=node, message=message, verbose=verbose, capture_output=True)

def extract_psql_value(psql_output: str, alias: str) -> str:
    lines = psql_output.split('\n')
    if len(lines) < 3:
        return ""
    header_line = lines[0]
    headers = [header.strip() for header in header_line.split('|')]

    alias_index = -1
    for i, header in enumerate(headers):
        if header == alias:
            alias_index = i
            break

    if alias_index == -1:
        return ""

    for line in lines[2:]:
        if line.strip() == "":
            continue
        columns = [column.strip() for column in line.split('|')]
        if len(columns) > alias_index:
            return columns[alias_index]

    return ""


def set_cluster_readonly(nodes, readonly, dbname, stanza, verbose):
    action = "Setting" if readonly else "Removing"
    func_call = ("spock.set_cluster_readonly()" if readonly
                 else "spock.unset_cluster_readonly()")

    sql_cmd = f"SELECT {func_call}"

    for node in nodes:
        cmd = f"{node['path']}/pgedge/pgedge psql '{sql_cmd}' {dbname}"
        message = f"{action} readonly mode from cluster"
        run_cmd(cmd, node=node, message=message, verbose=verbose, important=True)

def check_cluster_lag(n, dbname, stanza, verbose, timeout=600, interval=1):
    sql_cmd = """
    SELECT COALESCE(
    (SELECT pg_wal_lsn_diff(pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn())),
    0
    ) AS lag_bytes
    """

    start_time = time.time()
    lag_bytes = 1

    while lag_bytes > 0:
        if time.time() - start_time > timeout:
            return

        cmd = f"{n['path']}/pgedge/pgedge psql '{sql_cmd}' {dbname}"
        message = f"Checking lag time of new cluster"
        result = run_cmd(cmd = cmd, node=n, message=message, verbose=verbose, capture_output=True)
        print(result.stdout)
        lag_bytes = int(extract_psql_value(result.stdout, "lag_bytes"))

def check_wal_rec(n, dbname, stanza, verbose, timeout=600, interval=1):
    sql_cmd = """
    SELECT
        COALESCE(SUM(CASE
            WHEN pub.confirmed_flush_lsn <= sub.latest_end_lsn THEN 1
            ELSE 0
        END), 0) AS total_all_flushed
    FROM
        pg_stat_subscription AS sub
    JOIN
        pg_replication_slots AS pub ON sub.subname = pub.slot_name
    WHERE
        pub.slot_name IS NOT NULL
    """

    lag_bytes = 1
    start_time = time.time()

    while lag_bytes > 0:
        if time.time() - start_time > timeout:
            return

        cmd = f"{n['path']}/pgedge/pgedge psql '{sql_cmd}' {dbname}"
        message = "Checking wal receiver"
        result = run_cmd(cmd = cmd, node=n, message=message, verbose=verbose, capture_output=True)
        time.sleep(interval)
        lag_bytes = int(extract_psql_value(result.stdout, "total_all_flushed"))


def replication_all_tables(cluster_name, database_name=None):
    """Add all tables in the database to replication on every node"""
    db, db_settings, nodes = load_json(cluster_name)
    db_name=None
    if database_name is None:
        db_name=db[0]["db_name"]
    else:
        for i in db:
            if i["db_name"]==database_name:
                db_name=database_name
    if db_name is None:
        util.exit_message(f"Could not find information on db {database_name}")

    if "auto_ddl" in db_settings:
        if db_settings["auto_ddl"] == "on":
            util.exit_message(f"Auto DDL enabled for db {database_name}")

    for n in nodes:
        ndpath = n["path"]
        nc = ndpath + os.sep + "pgedge" + os.sep + "pgedge"
        ndip = n["public_ip"]
        os_user = n["os_user"]
        ssh_key = n["ssh_key"]
        cmd = f"{nc} spock repset-add-table default '*' {db_name}"
        util.echo_cmd(cmd, host=ndip, usr=os_user, key=ssh_key)


def replication_check(cluster_name, show_spock_tables=False, database_name=None):
    """Print replication status on every node"""
    db, db_settings, nodes = load_json(cluster_name)
    db_name=None
    if database_name is None:
        db_name=db[0]["db_name"]
    else:
        for i in db:
            if i["db_name"]==database_name:
                db_name=database_name
    if db_name is None:
        util.exit_message(f"Could not find information on db {database_name}")
    for n in nodes:
        ndpath = n["path"]
        nc = ndpath + os.sep + "pgedge" + os.sep + "pgedge"
        ndip = n["public_ip"]
        os_user = n["os_user"]
        ssh_key = n["ssh_key"]
        if show_spock_tables == True:
            cmd = f"{nc} spock repset-list-tables '*' {db_name}"
            util.echo_cmd(cmd, host=ndip, usr=os_user, key=ssh_key)
        cmd = f"{nc} spock sub-show-status '*' {db_name}"
        util.echo_cmd(cmd, host=ndip, usr=os_user, key=ssh_key)


def command(cluster_name, node, cmd, args=None):
    """Run './pgedge' commands on one or 'all' nodes.
    
       Run './pgedge' commands on one or all of the nodes in a cluster. 
       This command requires a JSON file with the same name as the cluster to be in the cluster/<cluster_name>. \n 
       Example: cluster command demo n1 "status"
       Example: cluster command demo all "spock repset-add-table default '*' db[0]["name"]"
       :param cluster_name: The name of the cluster.
       :param node: The node to run the command on. Can be the node name or all.
       :param cmd: The command to run on every node, excluding the beginning './pgedge' 
    """

    db, db_settings, nodes = load_json(
        cluster_name
    )
    rc = 0
    knt = 0
    for nd in nodes:
        if node == "all" or node == nd["name"]:
            knt = knt + 1
            rc = util.echo_cmd(
                nd["path"] + os.sep + "pgedge" + os.sep + "pgedge " + cmd,
                host=nd["public_ip"],
                usr=nd["os_user"],
                key=nd["ssh_key"],
            )

    if knt == 0:
        util.message("# nothing to do")

    return rc


def app_install(cluster_name, app_name, database_name=None, factor=1):
    """Install test application [ pgbench | northwind ].
    
       Install a test application on all of the nodes in a cluster. 
       This command requires a JSON file with the same name as the cluster to be in the cluster/<cluster_name>. \n 
       Example: cluster app-install pgbench
       :param cluster_name: The name of the cluster.
       :param node: The application name, pgbench or northwind.
       :param factor: The scale flag for pgbench.
    """
    db, db_settings, nodes = load_json(
            cluster_name
        )
    db_name=None
    if database_name is None:
        db_name=db[0]["db_name"]
    else:
        for i in db:
            if i["db_name"]==database_name:
                db_name=database_name
    if db_name is None:
        util.exit_message(f"Could not find information on db {database_name}")
    ctl =  os.sep + "pgedge" + os.sep + "pgedge"
    if app_name == "pgbench":
        for n in nodes:
            ndpath = n["path"]
            ndip = n["public_ip"]
            util.echo_cmd(f"{ndpath}{ctl} app pgbench-install {db_name} {factor} default", host=ndip, usr=n["os_user"], key=n["ssh_key"])
    elif app_name == "northwind":
        for n in nodes:
            ndpath = n["path"]
            ndip = n["public_ip"]
            util.echo_cmd(f"{ndpath}{ctl} app northwind-install {db_name} default", host=ndip, usr=n["os_user"], key=n["ssh_key"])
    else:
        util.exit_message(f"Invalid app_name '{app_name}'.")


def ssh_un_cross_wire(cluster_name, db, db_settings, db_user, db_passwd, nodes):
    """Create nodes and subs on every node in a cluster."""
    sub_array=[]
    for prov_n in nodes:
        ndnm = prov_n["name"]
        ndpath = prov_n["path"]
        nc = ndpath + os.sep + "pgedge" + os.sep + "pgedge"
        ndip = prov_n["public_ip"]
        os_user = prov_n["os_user"]
        ssh_key = prov_n["ssh_key"]
        for sub_n in nodes:
            sub_ndnm = sub_n["name"]
            if sub_ndnm != ndnm:
                cmd = f"{nc} spock sub-drop sub_{ndnm}{sub_ndnm} {db}"
                util.echo_cmd(cmd, host=ndip, usr=os_user, key=ssh_key)

    for prov_n in nodes:
        ndnm = prov_n["name"]
        ndpath = prov_n["path"]
        nc = ndpath + os.sep + "pgedge" + os.sep + "pgedge"
        ndip = prov_n["public_ip"]
        os_user = prov_n["os_user"]
        ssh_key = prov_n["ssh_key"]
        cmd1 = f"{nc} spock node-drop {ndnm} {db}"
        util.echo_cmd(cmd1, host=ndip, usr=os_user, key=ssh_key)
    ## To Do: Check Nodes have been dropped


def app_remove(cluster_name, app_name, database_name=None):
    """Remove test application from cluster.
    
       Remove a test application from all of the nodes in a cluster. 
       This command requires a JSON file with the same name as the cluster to be in the cluster/<cluster_name>. \n 
       Example: cluster app-remove pgbench
       :param cluster_name: The name of the cluster.
       :param node: The application name, pgbench or northwind.
    """
    db, db_settings, nodes = load_json(
            cluster_name
        )
    db_name=None
    if database_name is None:
        db_name=db[0]["db_name"]
    else:
        for i in db:
            if i["db_name"]==database_name:
                db_name=database_name
    if db_name is None:
        util.exit_message(f"Could not find information on db {database_name}")
    ctl =  os.sep + "pgedge" + os.sep + "pgedge"
    if app_name == "pgbench":
         for n in nodes:
            ndpath = n["path"]
            ndip = n["public_ip"]
            util.echo_cmd(f"{ndpath}{ctl} app pgbench-remove {db_name}", host=ndip, usr=n["os_user"], key=n["ssh_key"])
    elif app_name == "northwind":
         for n in nodes:
            ndpath = n["path"]
            ndip = n["public_ip"]
            util.echo_cmd(f"{ndpath}{ctl} app northwind-remove {db_name}", host=ndip, usr=n["os_user"], key=n["ssh_key"])
    else:
        util.exit_message("Invalid application name.")

def list_nodes(cluster_name):
    """List all nodes in the cluster."""
    db, db_settings, nodes = load_json(cluster_name)

    nodes_list = []
    for node in nodes:
        node_info = (
            f"Node: {node['name']}, IP: {node['public_ip']}, "
            f"Port: {node['port']}, Active: {'Yes' if node['is_active'] else 'No'}"
        )
        nodes_list.append(node_info)

    return nodes_list

def validate_json(json_data):
    required_keys = {
        "node_groups": {
            "dynamic_key": [
                {
                    "nodes": [
                        {
                            "name": str,
                            "is_active": bool,
                            "public_ip": str,
                            "port": int,
                            "repo1_type": str,
                            "path": str
                        }
                    ]
                }
            ]
        }
    }

    valid_node_groups = {"aws", "localhost", "azure", "gcp", "remote"}
    valid_repo1_types = {"s3", "posix"}

    def validate_keys(data, template, path=""):
        if isinstance(template, dict):
            if not isinstance(data, dict):
                util.exit_message(
                    f"Expected a dictionary at {path}, but got {type(data).__name__}.", 1
                )
            for key, sub_template in template.items():
                if key == "dynamic_key":
                    for dynamic_key in data.keys():
                        if dynamic_key not in valid_node_groups:
                            util.exit_message(
                                f"Invalid node group '{dynamic_key}' at {path}.", 1
                            )
                        validate_keys(
                            data[dynamic_key], sub_template,
                            path + f".{dynamic_key}"
                        )
                else:
                    if key not in data:
                        util.exit_message(f"Missing key '{key}' at {path}.", 1)
                    validate_keys(data[key], sub_template, path + f".{key}")
        elif isinstance(template, list):
            if not isinstance(data, list):
                util.exit_message(
                    f"Expected a list at {path}, but got {type(data).__name__}.", 1
                )
            if len(template) > 0:
                for index, item in enumerate(data):
                    validate_keys(item, template[0], path + f"[{index}]")
        else:
            if not isinstance(data, template):
                util.exit_message(
                    f"Expected {template.__name__} at {path}, but got {type(data).__name__}.", 1
                )
            if path.endswith(".repo1_type") and data not in valid_repo1_types:
                util.exit_message(f"Invalid repo1_type '{data}' at {path}.", 1)

    validate_keys(json_data, required_keys)


def print_install_hdr(cluster_name, db, db_user, count, name, path, ip, port, repo):

    node = {
        "REPO": repo,
        "Cluster Name": cluster_name,
        "Name": name,
        "Host": ip,
        "Port": port,
        "Path": path,
        "Database": db,
        "Database User": db_user,
        "Number of Nodes": count,
    }
    util.echo_node(node)

if __name__ == "__main__":
    fire.Fire(
        {
            "json-validate": json_validate,
            "json-create": json_create,
            "json-template": json_create,  # Map json-template to the json_create function
            "init": init,
            "list-nodes": list_nodes,
            "add-node": add_node,
            "remove-node": remove_node,
            "replication-begin": replication_all_tables,
            "replication-check": replication_check,
            "add-db": add_db,
            "remove": remove,
            "command": command,
            "set-firewalld": set_firewalld,
            "ssh": ssh,
            "app-install": app_install,
            "app-remove": app_remove
        }
    )
