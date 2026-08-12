# This SHOULD NOT BE RERUN unless you are retraining.
# It only needs to be rerun when new players are added that are worth modeling directly

import pandas as pd
import os
import json

print(os.getcwd())
os.chdir("../data")

## Set the data directory here

df = pd.read_csv("agg.csv" )

pid_map = { pid: i for i, pid in enumerate(df["Player ID"].unique())}
#df["pid"] = df["Player ID"].map(pid_map)

Nplayers = len(pid_map)

print("New Number of Players is" , Nplayers)

with open("player_map.json", "w") as writer:
    json.dump(pid_map, writer, indent=1)
print("DONE")