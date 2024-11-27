#!/usr/bin/env python3

#####################################################
#  Copyright 2022-2023 PGEDGE  All rights reserved. #
#####################################################

import os
import json
import util
import fire
import time

base_dir = "cluster"

def start(verbose=False):
    util.run_rcommand(
        f"sudo systemctl daemon-reload", 
        message="", verbose=verbose
    )
    time.sleep(3)
    util.run_rcommand(
        f"sudo systemctl start etcd", 
        message="", verbose=verbose
    )

def stop(verbose=False):
    util.run_rcommand(
        f"sudo systemctl stop etcd", 
        message="", verbose=verbose
    )

def status(verbose=False):
    util.run_rcommand(
        f"sudo systemctl status etcd", 
        message="", verbose=verbose
    )

if __name__ == "__main__":
    fire.Fire({
        "start": start,
        "stop": stop,
        "status": status,
    })

