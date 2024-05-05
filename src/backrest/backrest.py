#!/usr/bin/env python3
import subprocess
import os
import fire
import util
import time
import utilx
import json
import sys
from datetime import datetime
from tabulate import tabulate

def pgV():
    """Return the first found among supported PostgreSQL versions."""
    pg_versions = ["pg14", "pg15", "pg16"]
    for pg_version in pg_versions:
        if os.path.isdir(pg_version):
            return pg_version
    sys.exit("pg14, 15 or 16 must be installed")

def osSys(p_input, p_display=True):
    """Execute a shell command and optionally display it."""
    if p_display:
        util.message("# " + p_input)
    return os.system(p_input)

def fetch_backup_config():
    """Fetch and return the pgBackRest configuration from system settings."""
    config = {
        "main": {},
        "global": {},
        "stanza": {}
    }

    main_params = ["restore_path", "backup-type", "stanza_count"]
    global_params = [
        "repo1-retention-full", "repo1-retention-full-type", "repo1-path",
        "repo1-cipher-type", "repo1-cipher-pass", "repo1-s3-bucket", "repo1-s3-key-secret", "repo1-s3-key",
        "repo1-s3-region", "repo1-s3-endpoint", "log-level-console", "repo1-type",
        "process-max", "compress-level"
    ]
    stanza_params = [
        "pg1-path", "pg1-user", "pg1-database", "db-socket-path", "pg1-port", "pg1-host"
    ]

    # Fetch main and global parameters
    for param in main_params:
        config["main"][param] = util.get_value("BACKUP", param)
    for param in global_params:
        config["global"][param] = util.get_value("BACKUP", param)

    # Determine the number of stanzas and fetch their specific parameters
    stanza_count = int(config["main"].get("stanza_count", 1))
    for i in range(stanza_count):
        stanza_name = util.get_value("BACKUP", f"stanza{i}")
        config["stanza"][stanza_name] = {}
        for param in stanza_params:
            indexed_param = f"{param}{i}"
            config["stanza"][stanza_name][param] = util.get_value("BACKUP", indexed_param)

    return config

def show_config():
    """Display the current configuration in a readable format."""
    config = fetch_backup_config()  # Fetches the full configuration from wherever it's stored
    max_key_length = max(max(len(key) for key in section) for section in config.values() if section)

    # Print section with adequate formatting based on the maximum key length
    print("#" * (max_key_length + 60))

    main  = config["main"]
    print(f"[main]")
    for key, value in main.items():
        print(f"{key.ljust(max_key_length + 20)}= {value}")

    print("\n")
    
    glob = config["global"]
    print(f"[global]")
    for key, value in glob.items():
        print(f"{key.ljust(max_key_length + 20)}= {value}")

    stanza_count = int(config["main"].get("stanza_count", 1))
    for i in range(stanza_count):
        stanza_name = util.get_value("BACKUP", f"stanza{i}")
        print("\n")
        print(f"[{stanza_name}]")
        print("----")
        for key, value in config["stanza"][stanza_name].items():
            clean_key = key.replace(str(i), '') 
            print(f"{clean_key.ljust(max_key_length + 20)}= {value}")
    
    print("#" * (max_key_length + 60))


def save_config(filename="pgbackrest.conf"):
    """Save the current pgBackRest configuration to a file in standard format."""
    config = fetch_backup_config()
    lines = []

    # Write global settings
    if config["global"]:
        lines.append("[global]")
        for key, value in config["global"].items():
            if key == "compress-level":
                continue  # Handle this key separately in its own section
            lines.append(f"{key} = {value}")
        lines.append("")  # Add a newline for separation

        # Handle global:archive-push specifically if needed
        if "compress-level" in config["global"]:
            lines.append("[global:archive-push]")
            lines.append(f"compress-level = {config['global']['compress-level']}")
            lines.append("")  # Add a newline for separation

    # Write stanza sections
    stanza_count = int(config["main"].get("stanza_count", 1))
    for i in range(stanza_count):
        stanza_name = util.get_value("BACKUP", f"stanza{i}")
        if stanza_name in config["stanza"]:
            lines.append(f"[{stanza_name}]")
            for key, value in config["stanza"][stanza_name].items():
                clean_key = key.replace(str(i), '')  # Remove the index from key names
                lines.append(f"{clean_key} = {value}")
            lines.append("")  # Add a newline for separation

    # Write the configuration to file
    with open(filename, "w") as f:
        f.write("\n".join(lines))
    util.message(f"Configuration saved to {filename}.")

    return filename



def backup(stanza, type="full"):
    """Perform a backup of a database cluster."""
    config = fetch_backup_config()
    if type not in ["full", "diff", "incr"]:
        util.message(f"Error: '{type}' is not a valid backup type. Allowed types are: full, diff, incr.")
        return

    command = [
        "pgbackrest", "--type", type, "backup", "--stanza", stanza
    ]
    utilx.run_command(command)

def restore(stanza, backup_label=None, recovery_target_time=None):
    """Restore a database cluster to a specified state."""
    config = fetch_backup_config()
    rpath = config["main"]["restore_path"]
    data_dir = os.path.join(rpath, stanza)

    print("Checking restore path directory and permissions ...")
    status = utilx.check_directory_status(data_dir)
    if not status['exists'] or not status['writable']:
        util.message(status['message'])
        return

    command = [
        "pgbackrest", "restore", "--stanza", stanza, "--pg1-path", data_dir
    ]
    if backup_label:
        command.append(f"--set={backup_label}")
    if recovery_target_time:
        command.append("--type=time")
        command.append(f"--target={recovery_target_time}")

    result = utilx.run_command(command)
    if result["success"]:
        util.message("Restoration completed successfully.")
    else:
        utilx.ereport('Error', 'Failed to restore cluster',
                      detail='Ensure the PostgreSQL instance is not running on that restore path',
                      context='Restore Cluster')
        sys.exit(1)

def pitr(stanza, recovery_target_time):
    """Perform point-in-time recovery on a database cluster."""
    print(f"Performing PIT recovery to {recovery_target_time}...")
    restore(stanza, recovery_target_time=recovery_target_time)
    _configure_pitr(stanza, recovery_target_time)

def _configure_pitr(stanza, recovery_target_time):
    """Configure PostgreSQL for point-in-time recovery."""
    config = fetch_backup_config()
    pg_data_dir = os.path.join(config["main"]["restore_path"], stanza, "data")
    config_file = os.path.join(pg_data_dir, "postgresql.conf")

    # Configuration changes for PITR
    changes = {
        "port": "5433",
        "log_directory": os.path.join(pg_data_dir, "log"),
        "archive_command": "",
        "archive_mode": "off",
        "hot_standby": "on",
        "recovery_target_time": recovery_target_time,
        "recovery_target_action": "promote"
    }

    for key, value in changes.items():
        change_pgconf_keyval(config_file, key, value)

def change_pgconf_keyval(config_path, key, value):
    """Edit a key-value pair in the PostgreSQL configuration file."""
    key_found = False
    with open(config_path, 'r') as file:
        lines = file.readlines()
    with open(config_path, 'w') as file:
        for line in lines:
            if line.strip().startswith(key):
                file.write(f"{key} = '{value}'\n")
                key_found = True
            else:
                file.write(line)
        if not key_found:
            file.write(f"{key} = '{value}'\n")

def create_replica(stanza, backup_label=None, do_backup=False):
    """Create a replica by restoring from a backup and configure it as a standby server."""
    if do_backup:
        backup(stanza, type="full")
    restore(stanza, backup_label)
    _configure_replica(stanza)

def _configure_replica(stanza):
    """Configure PostgreSQL to run as a replica (standby server)."""
    config = fetch_backup_config()
    pg_data_dir = os.path.join(config["main"]["restore_path"], stanza, "data")
    conf_file = os.path.join(pg_data_dir, "postgresql.conf")
    standby_signal = os.path.join(pg_data_dir, "standby.signal")

    # Connection info for the primary server should be configured prior to calling this function
    primary_conninfo = f"host={config['stanza'][stanza]['pg1-host']} port={config['stanza'][stanza]['pg1-port']} user=replication"

    # Configure postgresql.conf for replica
    changes = {
        "hot_standby": "on",
        "primary_conninfo": primary_conninfo,
        "port": "5433",
        "log_directory": os.path.join(pg_data_dir, "log"),
        "archive_command": "cd .",
        "archive_mode": "on"
    }

    for key, value in changes.items():
        change_pgconf_keyval(conf_file, key, value)
    
    # Create an empty standby.signal file to trigger standby mode
    open(standby_signal, 'a').close()

    util.message("Configuration for replica has been updated. Ensure the PostgreSQL instance is restarted.")

def list_backups():
    """List all available backups using pgBackRest."""
    config = fetch_backup_config()
    try:
        command_output = subprocess.check_output(
            ["pgbackrest", "info", "--output=json"],
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        backups_info = json.loads(command_output)

        backup_table = []
        for stanza_info in backups_info:
            for backup in stanza_info.get('backup', []):
                backup_details = [
                    stanza_info['name'],
                    backup.get('label', 'N/A'),
                    datetime.utcfromtimestamp(backup['timestamp']['start']).strftime('%Y-%m-%d %H:%M:%S'),
                    datetime.utcfromtimestamp(backup['timestamp']['stop']).strftime('%Y-%m-%d %H:%M:%S'),
                    backup.get('type', 'N/A'),
                    f"{backup.get('info', {}).get('size', 0) / (1024**3):.2f} GB"
                ]
                backup_table.append(backup_details)

        headers = ["Stanza Name", "Label", "Start Time", "End Time", "Type", "Size (GB)"]
        print(tabulate(backup_table, headers=headers, tablefmt="grid"))

    except subprocess.CalledProcessError as e:
        util.message(f"Error executing pgBackRest info command: {e.output}")

def modify_hba_conf(stanza):
  new_rules = [
      {
          "type": "host",
          "database": "replication",
          "user": "all",
          "address": "127.0.0.1/0",
          "method": "trust"
      }
  ]
  util.update_pg_hba_conf(stanza, new_rules)

def modify_postgresql_conf(stanza):
    """
    Modify 'postgresql.conf' to integrate with pgbackrest.
    """
    aCmd = f"pgbackrest --stanza={stanza} archive-push %p"
    util.change_pgconf_keyval(pgV(), "archive_command", aCmd, p_replace=True)
    util.change_pgconf_keyval(pgV(), "archive_mode", "on", p_replace=True)

def run_external_command(*args):
    """Execute an external pgBackRest command."""
    command = ["pgbackrest"] + list(args)
    result = utilx.run_command(command)
    if result["success"]:
        util.message("Command executed successfully.")
    else:
        utilx.ereport('Error', 'Command execution failed', detail=result["error"])

def validate_stanza_config(stanza_name, config):
    """
    Validate that all required parameters for a stanza are set.
    """
    required_params = ["pg1-path", "pg1-user", "pg1-database", "db-socket-path", "pg1-port", "pg1-host"]
    missing_params = [param for param in required_params if not config["stanza"].get(stanza_name, {}).get(param)]
    if missing_params:
        raise ValueError(f"Missing configuration parameters for stanza {stanza_name}: {', '.join(missing_params)}")
    return True

def create_stanza(stanza):
    """
    Create the required stanza for pgBackRest and configure PostgreSQL settings after ensuring all values are properly set.
    """
    # Fetch the current configuration
    config = fetch_backup_config()

    # Validate the configuration for the given stanza
    try:
        if validate_stanza_config(stanza, config):
            utilx.run_command([
                "pgbackrest", 
                "--stanza=" + stanza, 
                "stanza-create"
            ])
            util.message(f"Stanza {stanza} created successfully.")

            # Modify postgresql.conf to integrate with pgBackRest
            modify_postgresql_conf(stanza)
            # Modify pg_hba.conf to allow proper authentication for backup processes
            modify_hba_conf(stanza)

            # Restart the PostgreSQL service to apply changes
            cmd = f"./pgedge restart " + pgV()
            osSys(cmd)

    except Exception as e:
        utilx.ereport('Error', f'Failed to create or configure stanza {stanza}', detail=str(e))
        return


if __name__ == "__main__":
    fire.Fire({
        "backup": backup,
        "restore": restore,
        "pitr": pitr,
        "create-stanza": create_stanza,
        "create-replica": create_replica,
        "list-backups": list_backups,
        "show-config": show_config,
        "save-config": save_config,
        "command": run_external_command,
    })

