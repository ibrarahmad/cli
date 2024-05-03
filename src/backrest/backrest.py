#!/usr/bin/env python3
#     Copyright (c)  2022-2024 PGEDGE  #
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
    pg_versions = ["pg14", "pg15", "pg16"]

    for pg_version in pg_versions:
        if os.path.isdir(pg_version):
            return pg_version

    exit_rm_backrest("pg14, 15 or 16 must be installed")

def osSys(p_input, p_display=True):
    if p_display:
        util.message("# " + p_input)
def osSys(p_input, p_display=True):
    if p_display:
        util.message("# " + p_input)
    rc = os.system(p_input)
    return rc

def fetch_backup_config():
    """Fetch pgBackRest configuration."""
    config = {
        "main": {},
        "global": {},
        "stanza": {}
    }

    main_params = [
        "restore_path",
        "backup-type",
        "stanza_count"
    ]

    global_params = [
        "repo1-retention-full",
        "repo1-retention-full-type",
        "repo1-path",
        "repo1-cipher-type",
        "repo1-cipher-pass",
        "repo1-s3-bucket",
        "repo1-s3-region",
        "repo1-s3-endpoint",
        "log-level-console",
        "process-max",
        "compress-level"
    ]

    stanza_params = [
        "stanza",
        "pg1-path",
        "pg1-user",
        "pg1-database",
        "db-socket-path",
        "pg1-port",
        "pg1-host"
    ]
    # Fetching main parameters
    for param in main_params:
        config["main"][param] = util.get_value("BACKUP", param)

    # Fetching global parameters
    for param in global_params:
        config["global"][param] = util.get_value("BACKUP", param)

    stanza_count_value = util.get_value("BACKUP", "stanza_count")
    try:
        stanza_count = int(stanza_count_value)
    except (ValueError, TypeError):
        stanza_count = 1

    # Fetching stanza parameters
    for i in range(stanza_count):
        stanza_name = util.get_value("BACKUP", f"stanza")
        config["stanza"][stanza_name] = {}
        for param in stanza_params:
            config["stanza"][stanza_name][param] = util.get_value("BACKUP", f"{param}")

    return config

def save_config(filename="pgbackrest.conf"):
    """Dump the configuration to pgBackRest configuration file format."""
    config = fetch_backup_config()
    lines = []

    global_params = config.get("global", {})
    if global_params:
        lines.append("[global]")
        for key, value in global_params.items():
            if key.startswith("repo1-") or key in ["log-level-console", "process-max"]:
                lines.append(f"{key} = {value}")
            elif key == "compress-level":
                lines.append("")
                lines.append("[global:archive-push]")
                lines.append(f"{key} = {value}")
        lines.append("")

    # Write stanza sections
    stanza_sections = config.get("stanza", {})
    for stanza_name, stanza_params in stanza_sections.items():
        lines.append(f"[{stanza_name}]")
        for key, value in stanza_params.items():
            if key == "stanza":
                continue
            lines.append(f"{key} = {value}")
        lines.append("")

    with open(filename, "w") as f:
        f.write("\n".join(lines))


def show_config():
    """
    List configuration parameters configured for the backup tool.
    """
    config = fetch_backup_config()
    bold_start = "\033[1m"
    bold_end = "\033[0m"
    max_key_length = max(len(section) for section in config.keys())
    max_value_length = max(len(key) for section in config.values() for key in section.keys())
    line_length = max_key_length + max_value_length + 4

    # Print the top border
    print(bold_start + "#" * (line_length + 4) + bold_end)

    for section, parameters in config.items():
        print("[{}]".format(section))
        if section == "stanza":
            for stanza_name, stanza_params in parameters.items():
                print(f"[{stanza_name}]")
                for key, value in stanza_params.items():
                    print(f"{key.ljust(max_key_length)} = {value}")
                print()
        else:
            if not parameters:  # Check if parameters dictionary is empty
                print()
            else:
                for key, value in parameters.items():
                    print(f"{key} = {value}")
                print()

    # Print the bottom border
    print(bold_start + "#" * (line_length + 4) + bold_end)


def backup(stanza, type="full"):
    """
    Backup a database cluster.

    :param stanza: The name of the stanza to perform the backup on.
    :type stanza: str
    :param type: Specifies the type of backup to perform. This should be one of the following options:
                 - "full": Performs a full backup.
                 - "diff": Performs a differential backup.
                 - "incr": Performs an incremental backup.
                 Default is "full".
    :type type: str
    :return: None
    """
    config = fetch_backup_config()
    allowed_types = ["full", "diff", "incr"]
    if type not in allowed_types:
        util.message(f"Error: '{type}' is not a valid backup type. Allowed types are: {', '.join(allowed_types)}.")
        return

    command = [
        "pgbackrest",
        "--type", type, 
        "backup",
        "--stanza", stanza
    ]
    utilx.run_command(command)

def restore(stanza, backup_label=None, recovery_target_time=None):
    """
    Restore a database cluster.

    :param backup_label: The backup label to use for creating the
        replica. If not specified, the latest backup will be used.
    :type backup_label: str, optional

    :param recovery_target_time: The target time for point-in-time
        recovery (PITR). This allows the replica to be restored to
        a specific point in time, rather than the state at the time
        of the backup.
    :type recovery_target_time: str, optional.

    :return: None
    """
    pass

    config = fetch_backup_config()
    rpath = config["main"]["restore_path"]
    data_dir = rpath + f"/{stanza}/"

    print("Checking restore path directory and permissions ...")
    status = utilx.check_directory_status(rpath)
    if status['exists'] == True:
        if status['writable'] != True:
            util.message(status['message'])
            return

    command = [
        "pgbackrest",
        "restore",
        "--stanza", stanza,
        "--pg1-path", data_dir
    ]

    if status['exists'] == True:
        command.append("--delta")

    if backup_label:
        command.append("--set={}".format(backup_label))

    if recovery_target_time:
        formatted_time = utilx.sfmt_time(recovery_target_time)
        command.append(f"--type=time")
        command.append(f"--target={formatted_time}")

    result = utilx.run_command(command)
    if result["success"]:
        util.message("Restoration completed successfully.")
    else:
        utilx.ereport('Error', 'Failed to restore cluster',
        detail='Ensure the PostgreSQL instance is not running on that restore path',
        context='Restore Cluster')
        exit(1)
    return result

def _configure_pitr(stanza, recovery_target_time=None):
    config = fetch_backup_config()
    conf_file = os.path.join(config["RESTORE_PATH"], "data/postgresql.conf")
    logDir= config["RESTORE_PATH"] + "/log/"
    change_pgconf_keyval(conf_file, "port", "5433")
    change_pgconf_keyval(conf_file, "log_directory", logDir)
    change_pgconf_keyval(conf_file, "archive_command", "")
    change_pgconf_keyval(conf_file, "archive_mode", "off")
    change_pgconf_keyval(conf_file, "hot_standby", "on")
    change_pgconf_keyval(conf_file, "recovery_target_action", "promote",)

def change_pgconf_keyval(config_path, key, value):
    key_found = False
    new_lines = []
    with open(config_path, 'r') as file:
        lines = file.readlines()
        for line in lines:
            # Check if the line starts with the key
            if line.strip().startswith(key):
                new_lines.append(f"{key} = '{value}'\n")
                key_found = True
            else:
                new_lines.append(line)
    if not key_found:
        new_lines.append(f"{key} = '{value}'\n")

    with open(config_path, 'w') as file:
        file.writelines(new_lines)

def _configure_replica():
    config = fetch_backup_config()
    stanza = config["STANZA"]
    conf_file = os.path.join(config["RESTORE_PATH"] + "/data/", "postgresql.conf")
    standby_signal_path = os.path.join(config["RESTORE_PATH"] + "/data/", "standby.signal")
    logDir= config["RESTORE_PATH"] + "/log/"
    # Connection info for the primary server
    primary_conninfo = f"host={config['PRIMARY_HOST']} port={config['PRIMARY_PORT']} user={config['PRIMARY_USER']} password={config['REPLICA_PASSWORD']}"

    change_pgconf_keyval(conf_file, "primary_conninfo", primary_conninfo)
    change_pgconf_keyval(conf_file, "hot_standby", "on")
    change_pgconf_keyval(conf_file, "port", "5433")
    change_pgconf_keyval(conf_file, "log_directory", logDir)
    change_pgconf_keyval(conf_file, "archive_command", "")
    change_pgconf_keyval(conf_file, "archive_mode", "off")

    with open(standby_signal_path, "w") as _:
        pass

    utilx.ereport('WARNING', 'Configurations modified to configure as replica',
            detail='Ensure the PostgreSQL instance is restarted to apply these changes.',
            hint='./pgedge restart',
            context='Create Replica')


def pitr(backup_label=None, recovery_target_time=None):
    """
    Perfrom point-in-time recovery.

    :param backup_label: The backup label to use for creating the
        replica. If not specified, the latest backup will be used.
    :type backup_label: str, optional

    :param recovery_target_time: The target time for point-in-time
        recovery (PITR). This allows the replica to be restored to
        a specific point in time, rather than the state at the time of the backup.
    :type recovery_target_time: str, optional.

    :return: None
    """
    pass

    rtt = utilx.sfmt_time(recovery_target_time)
    config = fetch_backup_config()
    result = restore(backup_label, recovery_target_time)
    if result["success"]:
        _configure_pitr(config["stanza"], recovery_target_time)

def create_replica(backup_label=None, recovery_target_time=None, do_backup=False):
    """
    Create a replica by restoring from a backup and configure it.

    :param backup_label: The backup label to use for creating the replica.
        If not specified, the latest backup will be used.
    :type backup_label: str, optional

    :param recovery_target_time: The target time for point-in-time recovery (PITR).
        This allows the replica to be restored to a specific point in time, rather
        than the state at the time of the backup.
    :type recovery_target_time: str, optional

    :param do_backup: Whether to initiate a new backup before creating the replica.
        This can be used to ensure that the replica is as up-to-date as possible by
        creating a fresh backup from the primary before beginning the restoration process.
    :type do_backup: bool, optional

    :return: None
    """
    pass

    # If do_backup is True, initiate a backup before proceeding
    if do_backup:
      backup("full")

    restore(backup_label, recovery_target_time)

    # Configure the PostgreSQL instance as a replica
    _configure_replica()

def list_backups():
    """
    List backups using the configured backup tool.
    """
    config = fetch_backup_config()
    if config["BACKUP_TOOL"] == "pgbackrest":
        try:
            # Execute the pgbackrest info command with JSON output format
            command_output = subprocess.check_output([config["BACKUP_TOOL"], "info", "--output=json"],
                                                     stderr=subprocess.STDOUT, universal_newlines=True)
            backups_info = json.loads(command_output)

            # Prepare table data from backups info
            backup_table = []
            for stanza_info in backups_info:
                for backup in stanza_info.get('backup', []):
                    backup_details = [
                        stanza_info['name'],  # Stanza Name
                        backup.get('label', 'N/A'),  # Backup Label
                        datetime.utcfromtimestamp(backup['timestamp']['start']).strftime('%Y-%m-%d %H:%M:%S'),  # Start Time
                        datetime.utcfromtimestamp(backup['timestamp']['stop']).strftime('%Y-%m-%d %H:%M:%S'),  # End Time
                        backup.get('lsn', {}).get('start', 'N/A'),  # WAL Start
                        backup.get('lsn', {}).get('stop', 'N/A'),  # WAL End
                        backup.get('type', 'N/A'),  # Backup Type
                        f"{backup.get('info', {}).get('size', 0) / (1024**3):.2f} GB"  # Backup Size in GB
                    ]
                    backup_table.append(backup_details)

            # Print the backup table
            headers = ["Stanza Name", "Label", "Start Time", "End Time", "WAL Start", "WAL End", "Backup Type", "Size (GB)"]
            print(tabulate(backup_table, headers=headers, tablefmt="grid"))

        except subprocess.CalledProcessError as e:
            util.message(f"Error executing {config['BACKUP_TOOL']} info command:", e.output)
        except KeyError as ke:
            util.message(f"Error processing JSON data from {config['BACKUP_TOOL']}:", ke)
    else:
        util.message(f"The backup tool '{config['BACKUP_TOOL']}' does not support listing backups through this script.")

def run_external_command(*args):
    """
    Run pgbackrest with the given arguments.

    Example:  ./pgedge backrest command info
    """
    command = ["pgbackrest"] + list(args)
    utilx.run_command(command)

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

def create_stanza(stanza):
    """
    Create the required stanza data.
    """
    config = fetch_backup_config()
    if stanza not in config["stanza"]:
        utilx.ereport("ERROR", "Stanza must be configured in pgbackrest.conf")
        return

    command = [
        "pgbackrest",
        "--stanza=" + stanza,
        "stanza-create"
    ]
    utilx.run_command(command)

    modify_postgresql_conf(stanza)
    modify_hba_conf(stanza)

    osSys(f"pwd")
    osSys(f"./pgedge restart {stanza}")

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

