import os
import re
import json
import requests
import pandas as pd

directory_url = "https://ftp.nhc.noaa.gov/atcf/aid_public/"
response = requests.get(directory_url)
active_files = re.findall(r'href="(awp\d{2}2026\.dat\.gz)"', response.text)

discord_url = os.environ.get("DISCORD_WEBHOOK")

if not active_files:
    print("No active storms found in the Western Pacific.")
    with open("storm_track.json", "w") as f:
        json.dump({"status": "inactive", "name": "None", "track": []}, f)
else:
    latest_file = sorted(active_files)[-1]
    target_url = directory_url + latest_file

    column_names = [
        "BASIN", "CY", "DATE_TIME", "TECHNUM", "MODEL", "FORECAST_HOUR",
        "LAT", "LON", "VMAX", "MSLP", "TY", "RAD", "WINDCODE", "RAD1",
        "RAD2", "RAD3", "RAD4", "RADP", "RRP", "MRD", "GUSTS", "EYE",
        "SUBREGION", "MAXSEAS", "INITIALS", "DIR", "SPEED", "STORMNAME",
        "DEPTH", "SEAS", "SEASCODE", "SEAS1", "SEAS2", "SEAS3", "SEAS4"
    ]

    df = pd.read_csv(target_url, names=column_names, on_bad_lines="skip")
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)

    # Resolve Storm Name or Army/Navy designation
    all_names = df["STORMNAME"].dropna().unique()
    valid_names = [n for n in all_names if str(n).upper() not in ["NONAME", "INVEST", "NAN", ""]]
    cyclone_number = str(df["CY"].iloc[0]).zfill(2)

    display_name = f"Typhoon {valid_names[0].title()}" if valid_names else f"Tropical Cyclone {cyclone_number}W"

    # Extract consensus track model (TVCN)
    tvcn_df = df[df["MODEL"] == "TVCN"].copy()

    if not tvcn_df.empty:
        latest_run = tvcn_df["DATE_TIME"].max()
        latest_tvcn = tvcn_df[tvcn_df["DATE_TIME"] == latest_run].copy()

        def parse_coord(coord_str):
            if not isinstance(coord_str, str) or len(coord_str) < 2:
                return None
            val = float(coord_str[:-1]) / 10.0
            if coord_str[-1] in ["S", "W"]:
                val = -val
            return val

        latest_tvcn["lat"] = latest_tvcn["LAT"].apply(parse_coord)
        latest_tvcn["lon"] = latest_tvcn["LON"].apply(parse_coord)

        output_data = {
            "status": "active",
            "name": display_name,
            "run_time": str(latest_run),
            "track": latest_tvcn[["FORECAST_HOUR", "lat", "lon"]].to_dict(orient="records")
        }

        with open("storm_track.json", "w") as f:
            json.dump(output_data, f, indent=4)

        if discord_url:
            message = {
                "content": (
                    f"🚨 **{display_name} Update** 🚨\n"
                    f"New consensus forecast track published.\n"
                    f"**Model Run (UTC):** {latest_run}\n"
                    f"**Active Points:** {len(output_data['track'])}"
                )
            }
            requests.post(discord_url, json=message)
            print(f"Discord notification dispatched for {display_name}.")
