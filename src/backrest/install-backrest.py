#!/usr/bin/env python3
#     Copyright (c)  2022-2024 PGEDGE  #

import os
import subprocess
import time
import sys
import getpass
from crontab import CronTab
import subprocess
import util
import utilx

thisDir = os.path.dirname(os.path.realpath(__file__))
osUsr = util.get_user()
usrUsr = osUsr + ":" + osUsr

os.chdir(f"{thisDir}")

def exit_rm_backrest(msg):
    util.message(f"{msg}", "error")
    osSys(f"{thisDir}/pgedge remove backrest")
    sys.exit(1)


def pgV():
    pg_versions = ["pg14", "pg15", "pg16"]
    os.chdir(f"{thisDir}/../")
    for pg_version in pg_versions:
        if os.path.isdir(pg_version):
            return pg_version

    exit_rm_backrest("pg14, 15 or 16 must be installed")

def osSys(p_input, p_display=True):
    if p_display:
        util.message("# " + p_input)
    rc = os.system(p_input)
    return rc

def configure_backup_settings():
    stanza = "pg16"
    repo1_path = f"/var/lib/pgbackrest/"
    config = {
        "main": {
            "restore_path": "xx",
            "backup-type" : "full",
            "stanza_count" : "1"
        },
        "global": {
            "repo1-path": repo1_path,
            "repo1-cipher-pass": "xx",
            "repo1-cipher-type": "aes-256-cbc",
            "repo1-s3-bucket": "xx",
            "repo1-s3-region": "eu-west-2",
            "repo1-s3-key": "xx",
            "repo1-s3-key-secret": "xx",
            "repo1-s3-endpoint": "s3.amazonaws.com",
            "repo1-retention-full": "7",
            "repo1-retention-full-type": "count",
            "process-max" : "3",
            "log-level-console": "info"
        },
        "stanza": {
            "stanza" : "xx",
            "pg1-path" : "xx",
            "pg1-user" : "xx",
            "pg1-port" : "5432",
            "pg1-host" : "127.0.0.1",
            "global:archive-push": {
                "compress-level": "3"
            }
        }
    }
    for section, parameters in config.items():
        if isinstance(parameters, dict):
            for key, sub_params in parameters.items():
                if isinstance(sub_params, dict):
                    for sub_key, value in sub_params.items():
                        util.set_value(f"BACKUP", sub_key, value)
                else:
                    util.set_value("BACKUP", key, sub_params)
    
    print("Backup configuration has been set successfully.")


def setup_pgbackrest_links():
    """
    Set up symbolic link for pgbackrest and create necessary directories.
    """
    osSys("sudo rm -f /usr/bin/pgbackrest")
    osSys(f"sudo ln -s {thisDir}/bin/pgbackrest /usr/bin/pgbackrest")
    osSys("sudo chmod 755 /usr/bin/pgbackrest")

    osSys("sudo mkdir -p -m 770 /var/log/pgbackrest")

def setup_pgbackrest_conf():
    """
    Create pgbackrest configuration file and directories.
    """
    config = fetch_backup_config()
    usrUsr = osUsr
    dataDir = f"{thisDir}/../data"
    restoreDir = f"{thisDir}/../restore"

    osSys(f"sudo chown {usrUsr} /var/log/pgbackrest")
    osSys("sudo mkdir -p /etc/pgbackrest /etc/pgbackrest/conf.d")
    osSys("sudo cp pgbackrest.conf /etc/pgbackrest/")
    osSys("sudo chmod 640 /etc/pgbackrest/pgbackrest.conf")
    osSys(f"sudo chown {usrUsr} /etc/pgbackrest/pgbackrest.conf")

    osSys("sudo mkdir -p /var/lib/pgbackrest")
    osSys("sudo chmod 750 /var/lib/pgbackrest")
    osSys(f"sudo chown {usrUsr} /var/lib/pgbackrest")

    conf_file = thisDir + "/pgbackrest.conf"
    util.replace("pgXX", pgV(), conf_file, True)
    util.replace("pg1-path=xx", "pg1-path=" + dataDir, conf_file, True)
    util.replace("pg1-user=xx", "pg1-user=" + usrUsr, conf_file, True)
    util.replace("pg1-database=xx", "pg1-database=" + "postgres", conf_file, True)
    
    util.set_value("BACKUP", "stanza", pgV())
    util.set_value("BACKUP", "pg1-path", dataDir)
    util.set_value("BACKUP", "restore_path", restoreDir)
    util.set_value("BACKUP", "pg1-user", usrUsr)
    util.set_value("BACKUP", "pg1-database", "postgres")
    
    osSys("cp " + conf_file + "  /etc/pgbackrest/.")

def generate_cipher_pass():
    """
    Generate and replace cipher pass in pgbackrest.conf.
    """
    conf_file = os.path.join(thisDir, "pgbackrest.conf")
    cmd = "dd if=/dev/urandom bs=256 count=1 2> /dev/null | LC_ALL=C tr -dc 'A-Za-z0-9' | head -c32"
    bCipher = subprocess.check_output(cmd, shell=True)
    sCipher = bCipher.decode("ascii")
    util.replace("repo1-cipher-pass=xx", f"repo1-cipher-pass={sCipher}", conf_file, True)
    util.set_value("BACKUP", "repo1-cipher-pass", sCipher)

def modify_hba_conf():
  new_rules = [
      {
            "type": "host",
            "database": "replication",
            "user": "all",
            "address": "127.0.0.1/0",
            "method": "trust"
      }
  ]
  util.update_pg_hba_conf(pgV(), new_rules)

def create_or_update_job(crontab_lines, job_comment, detailed_comment, new_job):
    job_identifier = f"# {job_comment}"
    detailed_comment_line = f"# {detailed_comment}\n"
    job_exists = False

    for i, line in enumerate(crontab_lines):
        if job_identifier in line:
            crontab_lines[i] = job_identifier + "\n"
            if i + 1 < len(crontab_lines):
                crontab_lines[i + 1] = detailed_comment_line
                crontab_lines[i + 2] = new_job
            job_exists = True
            break

    if not job_exists:
        crontab_lines.extend([job_identifier + "\n", detailed_comment_line, new_job])

def define_cron_job():
    stanza = util.get_value("BACKUP", "stanza")
    full_backup_command = f"pgbackrest --stanza={stanza} --type=full backup"
    incr_backup_command = f"pgbackrest --stanza={stanza} --type=incr backup"
    expire_backup_command = f"pgbackrest --stanza={stanza} expire"

    run_as_user = 'root'

    # Crontab entries with detailed comments
    full_backup_cron = f"0 1 * * * {run_as_user} {full_backup_command}\n"
    incr_backup_cron = f"0 * * * * {run_as_user} {incr_backup_command}\n"
    expire_backup_cron = f"30 1 * * * {run_as_user} {expire_backup_command}\n"

    # Detailed comments for each job
    full_backup_comment = "Performs a full backup daily at 1 AM."
    incr_backup_comment = "Performs an incremental backup every hour."
    expire_backup_comment = "Manages backup retention, expiring old backups at 1:30 AM daily."

    system_crontab_path = "/etc/crontab"
    backrest_crontab_path = "backrest.crontab"

    with open(system_crontab_path, 'r') as file:
        existing_crontab = file.readlines()

    create_or_update_job(existing_crontab, "FullBackup", full_backup_comment, full_backup_cron)
    create_or_update_job(existing_crontab, "IncrementalBackup", incr_backup_comment, incr_backup_cron)
    create_or_update_job(existing_crontab, "ExpireBackup", expire_backup_comment, expire_backup_cron)

    with open(backrest_crontab_path, 'w') as file:
        file.writelines(existing_crontab)

    osSys(f"sudo cat {backrest_crontab_path} | sudo tee {system_crontab_path} > /dev/null", False)

def fetch_backup_config():
    """Fetch backrest configuration."""
    config = {
        "global": {},
        "stanza": {}
    }

    global_params = [
        "repo1-path",
        "pg1-path",
        "process-max",
        "repo1-retention-full",
        "repo1-retention-full-type",
        "log-level-console"
    ]

    stanza_params = [
        "stanza",
        "database",
        "pg1-socket-path",
        "pg1-user",
        "primary-port",
        "primary-host",
        "repo1-cipher-type",
        "restore-path",
        "backup-type",
        "s3-bucket",
        "s3-region",
        "s3-endpoint"
    ]

    for param in global_params:
        config["global"][param] = util.get_value("BACKUP", param)

    for param in stanza_params:
        config["stanza"][param] = util.get_value("BACKUP", param)

    return config

def print_header(header):
    bold_start = "\033[1m"
    bold_end = "\033[0m"
    print(bold_start + "##### " + header + " #####"+ bold_end)

def main():
    stanza = pgV()
    if os.path.isdir(f"/var/lib/pgbackrest/{stanza}/"):
        utilx.ereport("WARNING", "/var/lib/pgbackrest directory already exists")
    
    print_header("Configuring pgbackrest")
    configure_backup_settings()
    generate_cipher_pass()
    setup_pgbackrest_links()
    setup_pgbackrest_conf()
    usrUsr = f"{util.get_user()}:{util.get_user()}"
    print("pgbackrest installed successfully")

if __name__ == "__main__":
    main()

