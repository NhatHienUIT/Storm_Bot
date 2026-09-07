import os
import re
import json
import requests
import pandas as pd
import sys

directory_url = "https://ftp.nhc.noaa.gov/atcf/aid_public/"
print("Checking NOAA server for ALL global data...")
response = requests.get(directory_url)

# Grab absolutely every ATCF file on the server (Any basin, any number)
all_files = re.findall(r'href="(a?[a-z]{2}\d{2}\d{4}\.dat(?:\.gz)?)"', response.text)
all_files = list(set(all_files)) # Remove duplicates

discord_url = os.environ.get("DISCORD_WEBHOOK")

wp_storms_data = []
wp_discord_messages = []
other_storms_messages = []

column_names = [
    "BASIN", "CY", "DATE_TIME", "TECHNUM", "MODEL", "FORECAST_HOUR",
    "LAT", "LON", "VMAX", "MSLP", "TY", "RAD", "WINDCODE", "RAD1",
    "RAD2", "RAD3", "RAD4", "RADP", "RRP", "MRD", "GUSTS", "EYE",
    "SUBREGION", "MAXSEAS", "INITIALS", "DIR", "SPEED", "STORMNAME",
    "DEPTH", "SEAS", "SEASCODE", "SEAS1", "SEAS2", "SEAS3", "SEAS4"
]

for file_name in all_files:
    # Identify the basin from the filename (e.g., 'wp' = West Pacific, 'al' = Atlantic)
    basin_match = re.search(r'a?([a-z]{2})\d{2}', file_name)
    if not basin_match: continue
    basin_code = basin_match.group(1).lower()
    
    is_wp = (basin_code == 'wp')
    target_url = directory_url + file_name

    try:
        df = pd.read_csv(target_url, names=column_names, on_bad_lines="skip")
        if df.empty: continue
        df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
        
        is_invest = bool(re.search(r'9\d{5}\.dat', file_name))
        
        all_names = df["STORMNAME"].dropna().unique()
        valid_names = [n for n in all_names if str(n).upper() not in ["NONAME", "INVEST", "NAN", ""]]
        cyclone_number = str(df["CY"].iloc[0]).zfill(2)

        # Map basin codes to readable names
        basin_map = {"al": "Atlantic", "ep": "East Pacific", "cp": "Central Pacific", 
                     "wp": "West Pacific", "io": "Indian Ocean", "sh": "Southern Hemi"}
        basin_name = basin_map.get(basin_code, basin_code.upper())

        # Generate a clean name
        if is_invest:
            display_name = f"Invest {cyclone_number}{basin_code.upper()}"
        elif valid_names:
            display_name = f"{basin_name} Storm {valid_names[0].title()}"
        else:
            display_name = f"Cyclone {cyclone_number}{basin_code.upper()}"

        if is_wp:
            # Map Processing (Only for West Pacific)
            target_df = df[df["MODEL"] == "TVCN"].copy()
            if target_df.empty: target_df = df[df["MODEL"] == "OFCL"].copy()
            if target_df.empty: target_df = df[df["MODEL"] == "CARQ"].copy()

            if not target_df.empty:
                latest_run = target_df["DATE_TIME"].max()
                latest_track = target_df[target_df["DATE_TIME"] == latest_run].copy()

                def parse_coord(coord_str):
                    if not isinstance(coord_str, str) or len(coord_str) < 2: return None
                    val = float(coord_str[:-1]) / 10.0
                    if coord_str[-1] in ["S", "W"]: val = -val
                    return val

                latest_track["lat"] = latest_track["LAT"].apply(parse_coord)
                latest_track["lon"] = latest_track["LON"].apply(parse_coord)

                track_points = latest_track[["FORECAST_HOUR", "lat", "lon"]].dropna().to_dict(orient="records")

                wp_storms_data.append({
                    "name": display_name,
                    "run_time": str(latest_run),
                    "is_invest": is_invest,
                    "track": track_points
                })
                wp_discord_messages.append(f"• **{display_name}**: {len(track_points)} track points")
        else:
            # Dump into the "Other Storms" Discord list
            other_storms_messages.append(f"• **{display_name}** *(File: {file_name})*")

    except Exception as e:
        print(f"Skipping {file_name}: {e}")

# Save JSON map data
output_data = {"status": "active" if wp_storms_data else "inactive", "storms": wp_storms_data}
with open("storm_track.json", "w") as f:
    json.dump(output_data, f, indent=4)

# Build and Send the Discord Message
if discord_url:
    discord_body = ""
    
    # West Pacific Section
    if wp_discord_messages:
        discord_body += "🚨 **Western Pacific (Vietnam Basin)** 🚨\n" + "\n".join(wp_discord_messages) + "\n\n"
    else:
        discord_body += "✅ **Western Pacific** is currently clear on NOAA servers.\n\n"
        
    # Global Section
    if other_storms_messages:
        discord_body += "🌍 **Other Global Storms Tracked** 🌍\n" + "\n".join(other_storms_messages)
    else:
        discord_body += "🌍 **Other Global Storms**: None found."
        
    requests.post(discord_url, json={"content": discord_body})
    print("Global radar Discord alert sent.")
