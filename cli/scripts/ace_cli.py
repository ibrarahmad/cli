from datetime import datetime
import json
import ace_config as config
import ace_core
import ace_db
from ace_data_models import (
    RepsetDiffTask,
    SchemaDiffTask,
    SpockDiffTask,
    TableDiffTask,
    TableRepairTask,
)
import ace
import util
from ace_exceptions import AceException


"""
Performs a table diff operation on a specified cluster and table.

Args:
    cluster_name (str): Name of the cluster to perform the diff on.
    table_name (str): Name of the table to diff.
    dbname (str, optional): Name of the database. Defaults to None.
    block_rows (int, optional): Number of rows per block. Defaults to
        config.BLOCK_ROWS_DEFAULT.
    max_cpu_ratio (float, optional): Maximum CPU usage ratio. Defaults to
        config.MAX_CPU_RATIO_DEFAULT.
    output (str, optional): Output format. Defaults to "json".
    nodes (str, optional): Nodes to include in the diff. Defaults to "all".
    batch_size (int, optional): Size of each batch. Defaults to
        config.BATCH_SIZE_DEFAULT.
    quiet (bool, optional): Whether to suppress output. Defaults to False.

Raises:
    AceException: If there's an error specific to the ACE operation.
    Exception: For any unexpected errors during the table diff operation.

Returns:
    None. The function performs the table diff operation and handles any
    exceptions. All output messages are printed to stdout since it's a CLI
    function.
"""


def table_diff_cli(
    cluster_name,
    table_name,
    dbname=None,
    block_rows=config.BLOCK_ROWS_DEFAULT,
    max_cpu_ratio=config.MAX_CPU_RATIO_DEFAULT,
    output="json",
    nodes="all",
    batch_size=config.BATCH_SIZE_DEFAULT,
    quiet=False,
):

    task_id = ace_db.generate_task_id()

    try:
        raw_args = TableDiffTask(
            cluster_name=cluster_name,
            _table_name=table_name,
            _dbname=dbname,
            block_rows=block_rows,
            max_cpu_ratio=max_cpu_ratio,
            output=output,
            _nodes=nodes,
            batch_size=batch_size,
            quiet_mode=quiet,
        )
        raw_args.scheduler.task_id = task_id
        raw_args.scheduler.task_type = "table-diff"
        raw_args.scheduler.task_status = "RUNNING"
        raw_args.scheduler.started_at = datetime.now()

        td_task = ace.table_diff_checks(raw_args)
        ace_db.create_ace_task(task=td_task)
        ace_core.table_diff(td_task)
    except AceException as e:
        util.exit_message(str(e))
    except Exception as e:
        util.exit_message(f"Unexpected error while running table diff: {e}")


"""
Performs a table repair operation on a specified cluster and table.

Args:
    cluster_name (str): Name of the cluster to perform the repair on.
    diff_file (str): Path to the diff file generated by a previous table diff.
    source_of_truth (str): Node to be used as the source of truth for the repair.
    table_name (str): Name of the table to repair.
    dbname (str, optional): Name of the database. Defaults to None.
    dry_run (bool, optional): If True, simulates the repair without changes.
        Defaults to False.
    quiet (bool, optional): Whether to suppress output. Defaults to False.
    generate_report (bool, optional): If True, generates a detailed report of
        the repair. Defaults to False.
    upsert_only (bool, optional): If True, only performs upsert operations,
        skipping deletions. Defaults to False.

Raises:
    AceException: If there's an error specific to the ACE operation.
    Exception: For any unexpected errors during the table repair operation.

Returns:
    None. The function performs the table repair operation and handles any
    exceptions. All output messages are printed to stdout since it's a CLI
    function.
"""


def table_repair_cli(
    cluster_name,
    diff_file,
    source_of_truth,
    table_name,
    dbname=None,
    dry_run=False,
    quiet=False,
    generate_report=False,
    upsert_only=False,
):

    task_id = ace_db.generate_task_id()

    try:
        raw_args = TableRepairTask(
            cluster_name=cluster_name,
            diff_file_path=diff_file,
            source_of_truth=source_of_truth,
            _table_name=table_name,
            _dbname=dbname,
            dry_run=dry_run,
            quiet_mode=quiet,
            generate_report=generate_report,
            upsert_only=upsert_only,
        )
        raw_args.scheduler.task_id = task_id
        raw_args.scheduler.task_type = "table-repair"
        raw_args.scheduler.task_status = "RUNNING"
        raw_args.scheduler.started_at = datetime.now()
        tr_task = ace.table_repair_checks(raw_args)
        ace_db.create_ace_task(task=tr_task)
        ace_core.table_repair(tr_task)
    except AceException as e:
        util.exit_message(str(e))
    except Exception as e:
        util.exit_message(f"Unexpected error while running table repair: {e}")


"""
Reruns a table diff operation based on a previous diff file.

Args:
    cluster_name (str): Name of the cluster.
    diff_file (str): Path to the diff file from a previous table diff operation.
    table_name (str): Name of the table to rerun the diff on.
    dbname (str, optional): Name of the database. Defaults to None.
    quiet (bool, optional): Whether to suppress output. Defaults to False.
    behavior (str, optional): The rerun behavior, either "multiprocessing" or
        "hostdb". Defaults to "multiprocessing".

Raises:
    AceException: If there's an error specific to the ACE operation.
    Exception: For any unexpected errors during the table rerun operation.

Returns:
    None. The function performs the table rerun operation and handles any
    exceptions. All output messages are printed to stdout since it's a CLI
    function.
"""


def table_rerun_cli(
    cluster_name,
    diff_file,
    table_name,
    dbname=None,
    quiet=False,
    behavior="multiprocessing",
):

    task_id = ace_db.generate_task_id()

    try:
        raw_args = TableDiffTask(
            cluster_name=cluster_name,
            _table_name=table_name,
            _dbname=dbname,
            block_rows=config.BLOCK_ROWS_DEFAULT,
            max_cpu_ratio=config.MAX_CPU_RATIO_DEFAULT,
            output="json",
            _nodes="all",
            batch_size=config.BATCH_SIZE_DEFAULT,
            quiet_mode=quiet,
            diff_file_path=diff_file,
        )
        raw_args.scheduler.task_id = task_id
        raw_args.scheduler.task_type = "table-rerun"
        raw_args.scheduler.task_status = "RUNNING"
        raw_args.scheduler.started_at = datetime.now()
        td_task = ace.table_diff_checks(raw_args)
        ace_db.create_ace_task(task=td_task)
    except AceException as e:
        util.exit_message(str(e))
    except Exception as e:
        util.exit_message(f"Unexpected error while running table rerun: {e}")

    try:
        if behavior == "multiprocessing":
            ace_core.table_rerun_async(td_task)
        elif behavior == "hostdb":
            ace_core.table_rerun_temptable(td_task)
        else:
            util.exit_message(f"Invalid behavior: {behavior}")
    except AceException as e:
        util.exit_message(str(e))
    except Exception as e:
        util.exit_message(f"Unexpected error while running table rerun: {e}")


"""
Performs a repset diff operation on a specified cluster and repset.

Args:
    cluster_name (str): Name of the cluster.
    repset_name (str): Name of the repset to diff.
    dbname (str, optional): Name of the database. Defaults to None.
    block_rows (int, optional): Number of rows per block. Defaults to
        config.BLOCK_ROWS_DEFAULT.
    max_cpu_ratio (float, optional): Maximum CPU usage ratio. Defaults to
        config.MAX_CPU_RATIO_DEFAULT.
    output (str, optional): Output format. Defaults to "json".
    nodes (str, optional): Nodes to include in the diff. Defaults to "all".
    batch_size (int, optional): Size of each batch. Defaults to
        config.BATCH_SIZE_DEFAULT.
    quiet (bool, optional): Whether to suppress output. Defaults to False.
    skip_tables (list, optional): List of tables to skip. Defaults to None.

Raises:
    AceException: If there's an error specific to the ACE operation.
    Exception: For any unexpected errors during the repset diff operation.

Returns:
    None. The function performs the repset diff operation and handles any
    exceptions. All output messages are printed to stdout since it's a CLI
    function.
"""


def repset_diff_cli(
    cluster_name,
    repset_name,
    dbname=None,
    block_rows=config.BLOCK_ROWS_DEFAULT,
    max_cpu_ratio=config.MAX_CPU_RATIO_DEFAULT,
    output="json",
    nodes="all",
    batch_size=config.BATCH_SIZE_DEFAULT,
    quiet=False,
    skip_tables=None,
):

    task_id = ace_db.generate_task_id()

    try:
        raw_args = RepsetDiffTask(
            cluster_name=cluster_name,
            _dbname=dbname,
            repset_name=repset_name,
            block_rows=block_rows,
            max_cpu_ratio=max_cpu_ratio,
            output=output,
            _nodes=nodes,
            batch_size=batch_size,
            quiet_mode=quiet,
            invoke_method="CLI",
            skip_tables=skip_tables,
        )
        raw_args.scheduler.task_id = task_id
        raw_args.scheduler.task_type = "repset-diff"
        raw_args.scheduler.task_status = "RUNNING"
        raw_args.scheduler.started_at = datetime.now()
        rd_task = ace.repset_diff_checks(raw_args)
        ace_db.create_ace_task(task=rd_task)
        ace_core.repset_diff(rd_task)
    except AceException as e:
        util.exit_message(str(e))
    except Exception as e:
        util.exit_message(f"Unexpected error while running repset diff: {e}")


"""
Performs a spock diff operation on a specified cluster.

Args:
    cluster_name (str): Name of the cluster.
    dbname (str, optional): Name of the database. Defaults to None.
    nodes (str, optional): Nodes to include in the diff. Defaults to "all".
    quiet (bool, optional): Whether to suppress output. Defaults to False.

Raises:
    AceException: If there's an error specific to the ACE operation.
    Exception: For any unexpected errors during the spock diff operation.

Returns:
    None. The function performs the spock diff operation and handles any exceptions.
    All output messages are printed to stdout since it's a CLI function.
"""


def spock_diff_cli(
    cluster_name,
    dbname=None,
    nodes="all",
    quiet=False,
):

    task_id = ace_db.generate_task_id()

    try:
        raw_args = SpockDiffTask(
            cluster_name=cluster_name,
            _dbname=dbname,
            _nodes=nodes,
            quiet_mode=quiet,
        )
        raw_args.scheduler.task_id = task_id
        raw_args.scheduler.task_type = "spock-diff"
        raw_args.scheduler.task_status = "RUNNING"
        raw_args.scheduler.started_at = datetime.now()
        spock_diff_task = ace.spock_diff_checks(raw_args)
        ace_db.create_ace_task(task=spock_diff_task)
        ace_core.spock_diff(spock_diff_task)
    except AceException as e:
        util.exit_message(str(e))
    except Exception as e:
        util.exit_message(f"Unexpected error while running spock diff: {e}")


"""
Performs a schema diff operation on a specified cluster and schema.

Args:
    cluster_name (str): Name of the cluster.
    schema_name (str): Name of the schema to diff.
    nodes (str, optional): Nodes to include in the diff. Defaults to "all".
    dbname (str, optional): Name of the database. Defaults to None.
    quiet (bool, optional): Whether to suppress output. Defaults to False.

Raises:
    AceException: If there's an error specific to the ACE operation.
    Exception: For any unexpected errors during the schema diff operation.

Returns:
    None. The function performs the schema diff operation and handles any exceptions.
    All output messages are printed to stdout since it's a CLI function.
"""


def schema_diff_cli(cluster_name, schema_name, nodes="all", dbname=None, quiet=False):

    task_id = ace_db.generate_task_id()

    try:
        raw_args = SchemaDiffTask(
            cluster_name=cluster_name,
            schema_name=schema_name,
            _dbname=dbname,
            _nodes=nodes,
            quiet_mode=quiet,
        )
        raw_args.scheduler.task_id = task_id
        raw_args.scheduler.task_type = "schema-diff"
        raw_args.scheduler.task_status = "RUNNING"
        raw_args.scheduler.started_at = datetime.now()
        sd_task = ace.schema_diff_checks(raw_args)
        ace_db.create_ace_task(task=sd_task)
        ace_core.schema_diff(sd_task)
    except AceException as e:
        util.exit_message(str(e))
    except Exception as e:
        util.exit_message(f"Unexpected error while running schema diff: {e}")


def update_spock_exception_cli(cluster_name, node_name, entry, dbname=None) -> None:

    try:
        conn = ace.update_spock_exception_checks(cluster_name, node_name, entry, dbname)
        ace_core.update_spock_exception(entry, conn)
    except AceException as e:
        util.exit_message(str(e))
    except json.JSONDecodeError:
        util.exit_message("Exception entry is not a valid JSON")
    except Exception as e:
        util.exit_message(f"Unexpected error while running exception status: {e}")

    util.message("Spock exception status updated successfully", p_state="success")
