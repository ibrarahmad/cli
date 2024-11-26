from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

"""
Use a dataclass to store the raw and processed inputs from the user
"""


@dataclass
class Task:
    task_id: str = None
    task_type: str = None
    task_status: str = None
    task_context: str = None
    started_at: datetime = None
    finished_at: datetime = None
    time_taken: float = None


@dataclass
class DerivedFields:
    cluster_nodes: list = None
    l_schema: str = None
    l_table: str = None
    key: str = None
    cols: list = None
    conn_params: list = None
    database: str = None
    node_list: list = None
    host_map: dict = None
    table_list: list = None


@dataclass
class TableDiffTask:
    # Unprocessed fields
    _table_name: str  # Required
    _dbname: str
    _nodes: str

    # User-specified, validated fields
    cluster_name: str  # Required
    block_rows: int
    max_cpu_ratio: float
    output: str
    batch_size: int
    quiet_mode: bool

    # For table-diff, the diff_file_path is
    # obtained after the run of table-diff,
    # and is not mandatory
    diff_file_path: str = None

    # If we're invoking table-diff from repset-diff,
    # we don't need to update the database with the
    # status of each table-diff task (for now)
    skip_db_update: bool = False

    scheduler: Task = field(default_factory=Task)

    # Derived fields
    fields: DerivedFields = field(default_factory=DerivedFields)


@dataclass
class TableRepairTask:
    # Unprocessed fields
    _table_name: str
    _dbname: str

    # Mandatory fields
    cluster_name: str

    # For table-repair, the diff_file_path is
    # mandatory, as it is used to repair the
    # tables
    diff_file_path: str
    source_of_truth: str

    # Optional fields, but non-default since the handler method will fill in the
    # default values
    quiet_mode: bool
    dry_run: bool
    generate_report: bool
    upsert_only: bool

    # Task-specific parameters
    scheduler: Task = field(default_factory=Task)

    # Derived fields
    fields: DerivedFields = field(default_factory=DerivedFields)


@dataclass
class RepsetDiffTask:
    # Unprocessed fields
    _dbname: str
    _nodes: str

    # Mandatory fields
    cluster_name: str
    repset_name: str

    # Optional fields
    # Non-default members since the handler method will fill in the
    # default values
    block_rows: int
    max_cpu_ratio: float
    output: str
    batch_size: int
    quiet_mode: bool
    skip_tables: any

    invoke_method: str = "CLI"

    # Task-specific parameters
    scheduler: Task = field(default_factory=Task)

    # Derived fields
    fields: DerivedFields = field(default_factory=DerivedFields)


@dataclass
class SpockDiffTask:
    # Mandatory fields
    cluster_name: str

    # Optional fields
    # Non-default members since the handler method will fill in the
    # default values
    _nodes: str
    _dbname: str
    quiet_mode: bool

    # Task-specific parameters
    scheduler: Task = field(default_factory=Task)

    # Derived fields
    fields: DerivedFields = field(default_factory=DerivedFields)


@dataclass
class SchemaDiffTask:
    # Mandatory fields
    cluster_name: str
    schema_name: str

    # Optional fields
    # Non-default members since the handler method will fill in the
    # default values
    _nodes: str
    _dbname: str
    quiet_mode: bool

    # Task-specific parameters
    scheduler: Task = field(default_factory=Task)

    # Derived fields
    fields: DerivedFields = field(default_factory=DerivedFields)


@dataclass
class AutoRepairTask:
    remote_origin: int
    remote_commit_ts: datetime
    command_counter: int
    remote_xid: int
    local_origin: int
    local_commit_ts: datetime
    table_schema: str
    table_name: str
    operation: str
    local_tup: defaultdict
    remote_old_tup: defaultdict
    remote_new_tup: defaultdict
    ddl_statement: str
    ddl_user: str
    error_message: str
    retry_errored_at: datetime
