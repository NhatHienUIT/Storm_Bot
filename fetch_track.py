import os
import re
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

discord_url = os.environ.get("DISCORD_WEBHOOK")
wp_storms_data = []
wp_discord_messages = []

# --- METHOD 1: Try the ATCF Data Files ---
directory_url = "https://ftp.nhc.noaa.gov/atcf/aid_public/"
try:
    response = requests.get(directory_url, timeout=10)
    official_storms = re.findall(r'href="(a?wp[0-4]\d\d{4}\.dat(?:\.gz)?)"', response.text)
    invests = re.findall(r'href="(a?wp9\d\d{4}\.dat(?:\.gz)?)"', response.text)
    all_active_files = list(set(official_storms + invests))
except Exception:
    all_active_files = []

column_names = [
    "BASIN", "CY", "DATE_TIME", "TECHNUM", "MODEL", "FORECAST_HOUR",
    "LAT", "LON", "VMAX", "MSLP", "TY", "RAD", "WINDCODE", "RAD1",
    "RAD2", "RAD3", "RAD4", "RADP", "RRP", "MRD", "GUSTS", "EYE",
    "SUBREGION", "MAXSEAS", "INITIALS", "DIR", "SPEED", "STORMNAME",
    "DEPTH", "SEAS", "SEASCODE", "SEAS1", "SEAS2", "SEAS3", "SEAS4"
]

if all_active_files:
    for file_name in all_active_files:
        target_url = directory_url + file_name
        try:
            df = pd.read_csv(target_url, names=column_names, on_bad_lines="skip")
            df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
            
            is_invest = "wp9" in file_name.lower()
            
            all_names = df["STORMNAME"].dropna().unique()
            valid_names = [n for n in all_names if str(n).upper() not in ["NONAME", "INVEST", "NAN", ""]]
            cyclone_number = str(df["CY"].iloc[0]).zfill(2)

            if is_invest:
                display_name = f"Invest {cyclone_number}W"
            elif valid_names:
                display_name = f"Typhoon {valid_names[0].title()}"
            else:
                display_name = f"Tropical Cyclone {cyclone_number}W"

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

                if track_points:
                    wp_storms_data.append({
                        "name": display_name,
                        "run_time": str(latest_run),
                        "is_invest": is_invest,
                        "track": track_points
                    })
                    wp_discord_messages.append(f"• **{display_name}**: {len(track_points)} track points")
        except Exception:
            continue

# --- METHOD 2: The Aviation Text Fallback (GTS) ---
if not wp_storms_data:
    urls = [f"https://tgftp.nws.noaa.gov/data/raw/wt/wtpn3{i}.pgtw..txt" for i in range(1, 6)]
    now_utc = datetime.now(timezone.utc)
    
    for url in urls:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code != 200: continue
            text = r.text
            
            if "FINAL WARNING" in text: continue
            
            subj_match = re.search(r"SUBJ/(.*?) WARNING", text)
            if not subj_match: continue
            storm_name = subj_match.group(1).strip().title()
            
            time_match = re.search(r"WARNING POSITION:\s+(\d{2})(\d{2})(\d{2})Z", text)
            if not time_match: continue
            
            day, hour = int(time_match.group(1)), int(time_match.group(2))
            
            try:
                issue_date = now_utc.replace(day=day, hour=hour, minute=0, second=0, microsecond=0)
                if issue_date > now_utc + timedelta(days=1): 
                    issue_date = issue_date.replace(month=issue_date.month - 1)
            except Exception:
                continue

            if now_utc - issue_date > timedelta(hours=48):
                continue
                
            track_points = []
            
            def parse_text_coord(lat_str, lon_str):
                lat = float(lat_str[:-1])
                lon = float(lon_str[:-1])
                if lat_str[-1] == 'S': lat = -lat
                if lon_str[-1] == 'W': lon = -lon
                return lat, lon

            pos_match = re.search(r"WARNING POSITION:.*?NEAR\s+(\d+\.\d+[NS])\s+(\d+\.\d+[EW])", text, re.DOTALL)
            if pos_match:
                lat, lon = parse_text_coord(pos_match.group(1), pos_match.group(2))
                track_points.append({"FORECAST_HOUR": 0, "lat": lat, "lon": lon})
                
            forecasts = re.finditer(r"(\d{2})\s+HRS, VALID AT:.*?---\s+(\d+\.\d+[NS])\s+(\d+\.\d+[EW])", text, re.DOTALL)
            for f in forecasts:
                f_hour = int(f.group(1))
                lat, lon = parse_text_coord(f.group(2), f.group(3))
                track_points.append({"FORECAST_HOUR": f_hour, "lat": lat, "lon": lon})
            
            if track_points:
                wp_storms_data.append({
                    "name": storm_name,
                    "run_time": issue_date.strftime("%Y-%m-%d %H:%M UTC"),
                    "is_invest": False,
                    "track": track_points
                })
                wp_discord_messages.append(f"• **{storm_name}**: {len(track_points)} track points (Source: Aviation Text)")

        except Exception:
            continue

# --- 3. Save Map Data & Fire Webhook ---
output_data = {"status": "active" if wp_storms_data else "inactive", "storms": wp_storms_data}
with open("storm_track.json", "w") as f:
    json.dump(output_data, f, indent=4)

if discord_url and wp_discord_messages:
    joined_msgs = "\n".join(wp_discord_messages)
    message = {
        "content": f"🚨 **Multi-Storm Update** 🚨\nTracking {len(wp_storms_data)} active system(s) in the Western Pacific:\n{joined_msgs}"
    }
    requests.post(discord_url, json=message)
