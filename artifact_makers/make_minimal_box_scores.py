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

def get_team_and_period(table, verbose: bool = False) -> Tuple[str, str]:
    cap = table.caption.text
    if verbose: print("get_team_and_period", cap)
    cap = re.sub("Table", "", cap)
    if "Basic and Advanced Stats" in cap:
        period = "FG"
        team = re.sub(" Basic and Advanced Stats", "", cap)
        return team, period
    
    m = re.match(r"^(.*) \(([QH][1234])\)", cap)
    if m is None:
        return None, None
    return m.group(1), m.group(2)

def get_minimal_stats(soup: BeautifulSoup, filename: str, verbose=False) -> pd.DataFrame:
    ts = soup.find_all(name='table', class_='stats_table')

    dfs=[]
    for t in ts:
        if verbose: print("\t", t.caption.text)
        df = parseTable(t)
        if verbose and False: display(df)
        team, period = get_team_and_period(t)
        if verbose: print(team, period)
        if period is None:
            continue
        elif verbose:
            print("Got this far")
        df=df[["Player", "Player ID", "MP", "PTS"]]
        if period == "FG":
            df["Team"]=team
            df["Period"]=period
            dfs.append(df)
    df=pd.concat(dfs)
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
            
