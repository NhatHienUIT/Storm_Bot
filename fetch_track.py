import os
import re
import json
import requests
import pandas as pd
import sys

directory_url = "https://ftp.nhc.noaa.gov/atcf/aid_public/"
print("Checking NOAA server for Western Pacific data...")
response = requests.get(directory_url)

# Find ALL official storms and ALL invests
official_storms = re.findall(r'href="(awp[0-4]\d\d{4}\.dat\.gz)"', response.text)
invests = re.findall(r'href="(awp9\d\d{4}\.dat\.gz)"', response.text)

# Combine and remove duplicates
all_active_files = list(set(official_storms + invests))
discord_url = os.environ.get("DISCORD_WEBHOOK")

if not all_active_files:
    print("No active storms or invests found.")
    with open("storm_track.json", "w") as f:
        json.dump({"status": "inactive", "storms": []}, f)
    sys.exit()

all_storms_data = []
discord_messages = []

column_names = [
    "BASIN", "CY", "DATE_TIME", "TECHNUM", "MODEL", "FORECAST_HOUR",
    "LAT", "LON", "VMAX", "MSLP", "TY", "RAD", "WINDCODE", "RAD1",
    "RAD2", "RAD3", "RAD4", "RADP", "RRP", "MRD", "GUSTS", "EYE",
    "SUBREGION", "MAXSEAS", "INITIALS", "DIR", "SPEED", "STORMNAME",
    "DEPTH", "SEAS", "SEASCODE", "SEAS1", "SEAS2", "SEAS3", "SEAS4"
]

# Loop through every active storm/invest found
for file_name in all_active_files:
    target_url = directory_url + file_name
    
    try:
        df = pd.read_csv(target_url, names=column_names, on_bad_lines="skip")
        df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
        
        is_invest = "awp9" in file_name
        
        # Name resolution
        all_names = df["STORMNAME"].dropna().unique()
        valid_names = [n for n in all_names if str(n).upper() not in ["NONAME", "INVEST", "NAN", ""]]
        cyclone_number = str(df["CY"].iloc[0]).zfill(2)

        if is_invest:
            display_name = f"Invest {cyclone_number}W"
        elif valid_names:
            display_name = f"Typhoon {valid_names[0].title()}"
        else:
            display_name = f"Tropical Cyclone {cyclone_number}W"

        # Model Fallback Priority
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

            # Append this specific storm to our master list
            all_storms_data.append({
                "name": display_name,
                "run_time": str(latest_run),
                "is_invest": is_invest,
                "track": track_points
            })
            
            # Add a bullet point for this storm to the Discord summary
            discord_messages.append(f"• **{display_name}**: {len(track_points)} track points (Run: {latest_run})")
            
    except Exception as e:
        print(f"Skipping {file_name} due to parsing error: {e}")

# Save the combined array to JSON
output_data = {
    "status": "active",
    "storms": all_storms_data
}
with open("storm_track.json", "w") as f:
    json.dump(output_data, f, indent=4)
print(f"Saved {len(all_storms_data)} active systems to JSON.")

# Send one combined Discord Alert
if discord_url and discord_messages:
    joined_msgs = "\n".join(discord_messages)
    message = {
        "content": f"🚨 **Multi-Storm Update** 🚨\nTracking {len(all_storms_data)} active system(s) in the Western Pacific:\n{joined_msgs}"
    }
    requests.post(discord_url, json=message)
