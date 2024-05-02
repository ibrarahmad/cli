import sys, os, util_test, subprocess, json

# Print Script
print(f"Starting - {os.path.basename(__file__)}")

# Get Test Settings
util_test.set_env()
repo=os.getenv("EDGE_REPO")
cluster_dir=os.getenv("EDGE_CLUSTER_DIR")
port=int(os.getenv("EDGE_START_PORT",6432))
usr=os.getenv("EDGE_USERNAME","lcusr")
pw=os.getenv("EDGE_PASSWORD","password")
dbname=os.getenv("EDGE_DB","lcdb")

# Get a list of available packages - the list is returned in a json string:
get_list=("um list --json")
res=util_test.run_cmd("Getting list of available packages", get_list, f"{cluster_dir}/n1")
# Break the json string into a list:
res = json.loads(res.stdout)

# Loop through the results and install each available component:
for i, inner_list in enumerate(res): 
    comp=(res[i].get("component"))
    install_comp=(f"um install {comp} -U {usr} -P {pw} -d {dbname}")
    inst_res=util_test.run_cmd("Getting list of available packages", install_comp, f"{cluster_dir}/n1")

# List the installed components:
installed=(f"um list")
installed_res=util_test.run_cmd("Getting list of available packages", installed, f"{cluster_dir}/n1")
print(installed_res.stdout)


# Needle and Haystack
#Check for a returncode to confirm results:

if installed_res.returncode != 0:
    util_test.EXIT_FAIL
else:
    util_test.EXIT_PASS


