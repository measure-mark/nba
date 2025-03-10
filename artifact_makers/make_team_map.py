import re
import pandas as pd
import json

def extract_home_team_from_bs_filename(fn: str):
    m=re.search(r"\d0([A-Z]{3})\.html", fn)
    if not m:
        raise ValueError("Failed on " + fn)
    return m.group(1)


def get_most_common(series):
    return series.value_counts().index[0]

def make_map(df):
    # This takes in the box score dataset currently kept as agg.csv in data
    df["home_abrev"]=df.filename.apply(extract_home_team_from_bs_filename)

    hometeam_full_map=df.groupby("home_abrev").Team.apply(get_most_common).to_dict()
    with open("team_map.json", "w") as writer:
        json.dump(hometeam_full_map, writer, indent=1)