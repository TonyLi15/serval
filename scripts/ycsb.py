#!/usr/bin/env python3

import os
from sys import executable, argv

import pandas as pd
import numpy as np
import datetime


import module.plot as plot
import module.setting as setting

# EXECUTE THIS SCRIPT IN BASE DIRECTORY!!!

NUM_EXPERIMENTS_PER_SETUP = 10  # used in plot
VARYING_TYPE = "contention"  # used in plot

x_label = {
    "num_threads": "#thread",
    "reps": "#operations",
    "contention": "Skew",
    "MAX_SLOTS_OF_PER_CORE_BUFFER": "MAX_SLOTS_OF_PER_CORE_BUFFER",
    "NUM_TXS_IN_ONE_EPOCH": "NUM_TXS_IN_ONE_EPOCH"
}

protocol_id = {"CARACAL": 0, "SERVAL": 1}

protocols = ["caracal", "serval"]
CMAKE_BUILD_TYPE = "Release"

def parse_args():
    default_args = {
        "workload_type": "X",
        "num_records": 10000000,
        "num_threads": 64,
        "seconds": 1,
        "skews": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.99, 0.999],
        "reps_per_txn": 10
    }
    
    if len(argv) > 1:
        default_args["workload_type"] = argv[1]
        default_args["num_records"] = int(argv[2])
        default_args["num_threads"] = int(argv[3])
        default_args["seconds"] = int(argv[4])
        default_args["skews"] = list(map(float, argv[5].split(',')))
        default_args["reps_per_txn"] = int(argv[6])
    
    return default_args

def gen_setups(args):
    payloads = [4]
    buffer_slots = [4] # for caracal
    txs_in_epochs = [4096] # (1000epoch) (500epoch) (100epoch) respectively
    batch_core_bitmap_updates = [0] # 0 is good

    # workloads
    # X: Write-only A: 50:50 B 5:95
    workloads = [args["workload_type"]] 
    records = [args["num_records"]]
    threads = [args["num_threads"]]
    skews = args["skews"]
    repss = [args["reps_per_txn"]] # ここは変更しないでください！（未対応）

    return [
        [
            [protocol, str(payload), str(buffer_slot), str(txs_in_epoch), str(batch_core_bitmap_update)],
            {
                "protocol": protocol,
                "workload": workload,
                "record": record,
                "thread": thread,
                "skew": skew,
                "reps": reps
            }
        ]
        for protocol in protocols
        for payload in payloads
        for buffer_slot in buffer_slots
        for txs_in_epoch in txs_in_epochs
        for batch_core_bitmap_update in batch_core_bitmap_updates
        for workload in workloads
        for record in records
        for thread in threads
        for skew in skews
        for reps in repss
    ]


def build():
    if not os.path.exists("./build"):
        os.mkdir("./build")  # create build
    os.chdir("./build")
    if not os.path.exists("./log"):
        os.mkdir("./log")  # compile logs
    for setup in gen_setups(parse_args()):
        [[protocol, payload, buffer_slot, txs_in_epoch, batch_core_bitmap_update], _] = setup
        print("Compiling " + " PAYLOAD_SIZE=" + payload + " MAX_SLOTS_OF_PER_CORE_BUFFER=" + buffer_slot + " NUM_TXS_IN_ONE_EPOCH=" + txs_in_epoch + " BATCH_CORE_BITMAP_UPDATE=" + batch_core_bitmap_update)
        logfile = "_PAYLOAD_SIZE" + payload + "_MAX_SLOTS_OF_PER_CORE_BUFFER" + buffer_slot + ".compile_log"
        os.system(
            "cmake .. -DLOG_LEVEL=0 -DCMAKE_BUILD_TYPE="
            + CMAKE_BUILD_TYPE +
            " -DBENCHMARK=YCSB -DCC_ALG="
            + protocol.upper()
            + " -DPAYLOAD_SIZE="
            + payload
            + " -DMAX_SLOTS_OF_PER_CORE_BUFFER="
            + buffer_slot
            + " -DNUM_TXS_IN_ONE_EPOCH="
            + txs_in_epoch
            + " -DBATCH_CORE_BITMAP_UPDATE="
            + batch_core_bitmap_update
            + " > ./log/"
            + "compile_"
            + logfile
            + " 2>&1"
        )
        ret = os.system("make -j > ./log/" + logfile + " 2>&1")
        if ret != 0:
            print("Error. Stopping")
            exit(0)
    os.chdir("../")  # go back to base directory


def run_all():
    args = parse_args()
    os.chdir("./build/bin")  # move to bin
    if not os.path.exists("./res"):
        os.mkdir("./res")  # create result directory inside bin
        os.mkdir("./res/tmp")
    for setup in gen_setups(args):
        [
            [protocol, payload, buffer_slot, txs_in_epoch, batch_core_bitmap_update],
            run_args,
        ] = setup
        title = "ycsb" + payload + "_" + buffer_slot + "_" + txs_in_epoch + "_" + batch_core_bitmap_update + "_" + protocol

        print("[{}: {}]".format(title, " ".join([str(args["seconds"]), protocol, str(run_args["workload"]), str(run_args["record"]), str(run_args["thread"]), str(run_args["skew"]), str(run_args["reps"])])))

        for exp_id in range(NUM_EXPERIMENTS_PER_SETUP):
            dt_now = datetime.datetime.now()
            print(" Trial:" + str(exp_id))
            ret = os.system(
                # "numactl --interleave=all ./" # 多分これするとregionが壊れる
                "./"
                + title
                + " "
                + " ".join([str(args["seconds"]), protocol, str(run_args["workload"]), str(run_args["record"]), str(run_args["thread"]), str(run_args["skew"]), str(run_args["reps"]), str(exp_id)])
                + " > ./res/tmp/"
                + str(dt_now.isoformat())
                + " 2>&1"
            )
            if ret != 0:
                print("Error. Stopping")
                exit(0)
    ret = os.system(
        "cat ./res/*.csv > ./res/result.csv; cat ./res/header > ./res/concat.csv; cat ./res/result.csv >> ./res/concat.csv"
    )
    if ret != 0:
        print("Error. Stopping")
        exit(0)
    os.chdir("../../")  # back to base directory


def plot_all():
    path = "build/bin/res"
    # plot throughput
    os.chdir(path)  # move to result file

    header = pd.read_csv("header", sep=",").columns.tolist()
    compile_param = pd.read_csv("compile_params", sep=",").columns.tolist()
    runtime_param = pd.read_csv("runtime_params", sep=",").columns.tolist()
    df = pd.read_csv("result.csv", sep=",", names=header)
    print(df.info())
    runtime_protocols = df['protocol'].unique()

    dfs = {}
    grouped_dfs = {}
    for protocol in runtime_protocols:
        protocol_df = df[df["protocol"] == protocol]
        protocol_grouped_df = protocol_df.groupby(compile_param + runtime_param, as_index=False).sum()
        for column in protocol_grouped_df.columns:
            if column in ["TotalTime","InitializationTime","FinalizeInitializationTime","ExecutionTime","WaitInInitialization","WaitInExecution","PerfLeader","PerfMember"]:
                protocol_grouped_df[column] = protocol_grouped_df[column] / 64 / NUM_EXPERIMENTS_PER_SETUP
        grouped_dfs[protocol] = protocol_grouped_df
        dfs[protocol] = protocol_df

    if not os.path.exists("./plots"):
        os.mkdir("./plots")  # create plot directory inside res
    os.chdir("./plots")
    
    plot_params = ["TotalTime", "InitializationTime", "FinalizeInitializationTime", "ExecutionTime","WaitInInitialization","WaitInExecution","PerfLeader","PerfMember"]
    my_plot = plot.Plot(
        VARYING_TYPE,
        x_label,
        runtime_protocols,
        plot_params,  # change
    )  # change

    my_plot.plot_all_param_all_protocol(grouped_dfs)
    my_plot.plot_all_param_per_core("serval", dfs["serval"])
    #my_plot.plot_all_param_per_core("serval_BCBU", dfs["serval_BCBU"])
    my_plot.plot_all_param_per_core("caracal", dfs["caracal"])
    #my_plot.plot_all_param_per_core("serval", dfs["serval"])
    # my_plot.plot_cache_hit_rate(grouped_dfs)

    # my_plot.plot_cache_hit_rate(grouped_dfs)
    # my_plot.plot_all_param("caracal", grouped_dfs["caracal"])

    os.chdir("../../../../")  # go back to base directory


if __name__ == "__main__":
    build()
    run_all()
    plot_all()