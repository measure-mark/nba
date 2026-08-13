import random
import math
import numpy as np
import os
from bs4 import BeautifulSoup
import pandas as pd
import re
from typing import Tuple
import json

def get_team_names(soup: BeautifulSoup):
    h2_elements = soup.find_all('h2', string=re.compile("Basic and Advanced Stats"))

    team_names=[]
    # Print out the matching h2 elements
    for h2 in h2_elements:
        team_names.append(re.sub("Basic and Advanced Stats", "", h2.get_text()))
    return team_names

def parseTable(boxscore_table):
    # Extract the headers from the second row (ignoring the first row)
    header_row = boxscore_table.find_all('tr')[1]
    headers = [th.get_text() for th in header_row.find_all('th')[1:]]  # Skip the 'Rk' column

    # Extract player rows, skipping the first two header rows and 'reserves' rows
    player_rows = boxscore_table.find_all('tr')[2:]

    # Extract player stats for both teams, assign team names
    player_stats = []
    for row in player_rows:
        columns = row.find_all('td')
        if len(columns) > 0:
            player_name_tag = row.find('th').find('a')

            # Skip rows without player hyperlinks (team total rows)
            if player_name_tag:
                player_name = player_name_tag.get_text()
                player_id = player_name_tag['href'].split('/')[-1].split('.')[0]  # Extract player ID from the URL

                # Extract minutes played (first column of player stats)
                minutes_played = columns[0].get_text()
                if minutes_played != "DNP":  # Check if player played (e.g., skip "Did Not Play")
                    stats = [player_name, player_id] + [col.get_text() for col in columns]
                    player_stats.append(stats)
                else:
                    # If player did not play, add data with empty stats
                    stats = [player_name, player_id] + ['DNP' for _ in columns]
                    player_stats.append(stats)

    # Add 'Player', 'Player ID', and 'Team' as headers
    headers = ['Player', 'Player ID'] + headers


    # Create the DataFrame using the headers and player stats
    df = pd.DataFrame(player_stats, columns=headers)
    return df

# Box score tables carry a structured id, e.g.
#   box-ATL-game-basic   box-ATL-q1-basic   box-ATL-h2-basic   box-ATL-ot1-basic
# which is far steadier than the caption prose. The original parser read the caption,
# matching "<Team> Basic and Advanced Stats Table"; basketball-reference now writes
# "<Team> (0-1) Table", so every table fell through to (None, None) and the box score
# parsed to nothing at all -- for every league, not just WNBA.
TABLE_ID_RE = re.compile(r"^box-([A-Za-z0-9]{2,4})-(game|q[1-4]|h[12]|ot\d*)-basic$")


def get_team_and_period(table, verbose: bool = False) -> Tuple[str, str]:
    """Returns (team code, period). Period is "FG" for the full game.

    Overtime tables now resolve too -- they used to be dropped, which is the
    'Handle overtimes in parser' TODO.
    """
    m = TABLE_ID_RE.match(table.get("id") or "")
    if verbose:
        print("get_team_and_period", table.get("id"))
    if m is None:
        return None, None

    team, period = m.group(1).upper(), m.group(2)
    return team, "FG" if period == "game" else period.upper()


def get_team_name(table) -> str:
    """Full team name from the caption, with the win-loss record stripped.

    Kept because agg.csv's Team column has always held the full name, and
    team_map.json is keyed on it.
    """
    cap = table.caption.text if table.caption else ""
    cap = re.sub(r"\s*Table\s*$", "", cap)
    return re.sub(r"\s*\(\d+-\d+\)\s*$", "", cap).strip()

def get_minimal_stats(soup: BeautifulSoup, filename: str, verbose=False) -> pd.DataFrame:
    ts = soup.find_all(name='table', class_='stats_table')

    dfs=[]
    for t in ts:
        team_code, period = get_team_and_period(t)
        if verbose: print("\t", t.get("id"), team_code, period)
        if period != "FG":
            # Quarter/half/OT splits are dropped; we only keep the full-game table.
            continue
        df = parseTable(t)[["Player", "Player ID", "MP", "PTS"]]
        df["Team"] = get_team_name(t)
        df["Team Code"] = team_code
        df["Period"] = period
        dfs.append(df)

    if not dfs:
        raise ValueError(f"No full-game tables found in {filename}")

    df = pd.concat(dfs, ignore_index=True)
    df["filename"]=filename
    return df

def main():
    # make sure the home directory is cd'd to 
    header, write_mode = True, 'w'

    big_dfs = []
    for filename in os.listdir("."):
        m = re.match(r"^boxscores_\d{9}\w{3}\.html", filename)
        if not m:
            print("skipping", filename)
            continue
        
        with open(filename, "rb") as reader:
            page = reader.read()
        
        # Parse the HTML content of the page
        soup = BeautifulSoup(page, 'html.parser')
        df = get_minimal_stats(soup, filename)
        df.to_csv("agg.csv", header=header, index=False, mode= write_mode)
        header, write_mode = False, 'a'
            
