import os
import re
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

discord_url = os.environ.get("DISCORD_WEBHOOK")

wp_storms_map_data = []  
wp_official_msgs = []    
wp_invest_msgs = []      
global_msgs = []         

# --- METHOD 1: Try the ATCF Data Files for ALL Global Systems ---
directory_url = "https://ftp.nhc.noaa.gov/atcf/aid_public/"
try:
    response = requests.get(directory_url, timeout=10)
    all_files = re.findall(r'href="(a?[a-z]{2}\d{2}\d{4}\.dat(?:\.gz)?)"', response.text)
    all_files = list(set(all_files))
except Exception:
    all_files = []

column_names = [
    "BASIN", "CY", "DATE_TIME", "TECHNUM", "MODEL", "FORECAST_HOUR",
    "LAT", "LON", "VMAX", "MSLP", "TY", "RAD", "WINDCODE", "RAD1",
    "RAD2", "RAD3", "RAD4", "RADP", "RRP", "MRD", "GUSTS", "EYE",
    "SUBREGION", "MAXSEAS", "INITIALS", "DIR", "SPEED", "STORMNAME",
    "DEPTH", "SEAS", "SEASCODE", "SEAS1", "SEAS2", "SEAS3", "SEAS4"
]

basin_map = {"al": "Atlantic", "ep": "East Pacific", "cp": "Central Pacific", 
             "wp": "West Pacific", "io": "Indian Ocean", "sh": "Southern Hemi"}

# Words used for unnamed depressions
number_names = ["ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN", 
                "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN", "SIXTEEN", "SEVENTEEN", 
                "EIGHTEEN", "NINETEEN", "TWENTY"]

now_utc = datetime.now(timezone.utc)

if all_files:
    for file_name in all_files:
        match = re.search(r'a?([a-z]{2})(\d{2})', file_name)
        if not match: continue
        basin_code, cy_num = match.groups()
        
        is_wp = (basin_code == 'wp')
        is_invest = (int(cy_num) >= 90)
        
        if not is_wp and is_invest:
            continue
            
        target_url = directory_url + file_name
        try:
            df = pd.read_csv(target_url, names=column_names, on_bad_lines="skip")
            df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
            if df.empty: continue
            
            # --- 1. THE EXPIRATION FILTER ---
            # Check if the storm has been dead for more than 48 hours
            df["DATE_TIME"] = pd.to_numeric(df["DATE_TIME"], errors="coerce")
            latest_run_val = df["DATE_TIME"].max()
            if pd.isna(latest_run_val): continue
            
            try:
                latest_run_dt = datetime.strptime(str(int(latest_run_val)), "%Y%m%d%H").replace(tzinfo=timezone.utc)
                if (now_utc - latest_run_dt) > timedelta(hours=48):
                    continue # Skip this storm, it's dead
            except Exception:
                pass 
                
            # --- 2. THE SMART NAMING FILTER ---
            all_names = df["STORMNAME"].dropna().unique()
            valid_names = [n for n in all_names if str(n).upper() not in ["NONAME", "INVEST", "NAN", ""]]
            
            if is_invest:
                display_name = f"Invest {cy_num}{basin_code.upper()}"
            elif valid_names:
                first_name = valid_names[0].upper()
                if first_name in number_names or first_name.isdigit():
                    display_name = f"Tropical Depression {valid_names[0].title()}"
                else:
                    display_name = f"{valid_names[0].title()}"
            else:
                display_name = f"Cyclone {cy_num}{basin_code.upper()}"

            if is_wp:
                if not is_invest and valid_names and "Tropical Depression" not in display_name: 
                    display_name = f"Typhoon {display_name}"
                
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
                    
                    latest_track["VMAX"] = pd.to_numeric(latest_track["VMAX"], errors="coerce")
                    latest_track["MSLP"] = pd.to_numeric(latest_track["MSLP"], errors="coerce")
                    latest_track["DIR"] = pd.to_numeric(latest_track["DIR"], errors="coerce")
                    latest_track["SPEED"] = pd.to_numeric(latest_track["SPEED"], errors="coerce")
                    latest_track["FORECAST_HOUR"] = pd.to_numeric(latest_track["FORECAST_HOUR"], errors="coerce")
                    
                    track_points = latest_track[["FORECAST_HOUR", "lat", "lon"]].dropna(subset=["lat", "lon"]).to_dict(orient="records")

                    if track_points:
                        zero_hour = latest_track[latest_track["FORECAST_HOUR"] == 0]
                        curr_row = zero_hour.iloc[0] if not zero_hour.empty else latest_track.iloc[0]
                        
                        c_lat, c_lon = curr_row["lat"], curr_row["lon"]
                        c_vmax, c_mslp = curr_row["VMAX"], curr_row["MSLP"]
                        c_dir, c_spd = curr_row["DIR"], curr_row["SPEED"]
                        max_vmax = latest_track["VMAX"].max()

                        lat_str = f"{abs(c_lat)}°{'N' if c_lat>=0 else 'S'}" if pd.notna(c_lat) else "N/A"
                        lon_str = f"{abs(c_lon)}°{'E' if c_lon>=0 else 'W'}" if pd.notna(c_lon) else "N/A"
                        vmax_str = f"{int(c_vmax)} kt" if pd.notna(c_vmax) else "N/A"
                        max_vmax_str = f"{int(max_vmax)} kt" if pd.notna(max_vmax) else "N/A"

                        if pd.notna(c_dir) and pd.notna(c_spd):
                            movement_line = f"\n> **Movement:** {int(c_dir)}° at {int(c_spd)} kt"
                        elif pd.notna(c_spd) and c_spd == 0:
                            movement_line = "\n> **Movement:** Stationary"
                        else:
                            movement_line = ""

                        pressure_line = f"\n> **Pressure:** {int(c_mslp)} mb" if pd.notna(c_mslp) and c_mslp > 0 else ""

                        wp_storms_map_data.append({
                            "name": display_name,
                            "run_time": str(latest_run),
                            "is_invest": is_invest,
                            "track": track_points
                        })
                        
                        msg = (f"🔸 **{display_name}** (ATCF Data)\n"
                               f"> **Position:** {lat_str}, {lon_str}{movement_line}\n"
                               f"> **Intensity:** {vmax_str} (1-min){pressure_line}\n"
                               f"> **Forecast Peak:** {max_vmax_str}\n"
                               f"> **Track Points:** {len(track_points)}")
                               
                        if is_invest:
                            wp_invest_msgs.append(msg)
                        else:
                            wp_official_msgs.append(msg)
            
            else:
                df["VMAX"] = pd.to_numeric(df["VMAX"], errors="coerce")
                max_vmax = df["VMAX"].max()
                vmax_str = f" - Peak: {int(max_vmax)} kt" if pd.notna(max_vmax) else ""
                b_name = basin_map.get(basin_code, basin_code.upper())
                
                global_msgs.append(f"• **{display_name}** ({b_name}){vmax_str}")
                
        except Exception:
            continue

# --- METHOD 2: The Aviation Text Fallback (Only if Official WP files are missing) ---
if not wp_official_msgs:
    urls = [f"https://tgftp.nws.noaa.gov/data/raw/wt/wtpn3{i}.pgtw..txt" for i in range(1, 6)]
    
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

            if now_utc - issue_date > timedelta(hours=48): continue
                
            track_points = []
            def parse_text_coord(lat_str, lon_str):
                lat, lon = float(lat_str[:-1]), float(lon_str[:-1])
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
                f_lat, f_lon = parse_text_coord(f.group(2), f.group(3))
                track_points.append({"FORECAST_HOUR": f_hour, "lat": f_lat, "lon": f_lon})
            
            if track_points:
                all_winds = [int(w) for w in re.findall(r"MAX SUSTAINED WINDS\s+-\s+(\d+)\s+KT", text)]
                c_vmax = all_winds[0] if all_winds else None
                max_vmax = max(all_winds) if all_winds else None
                
                mslp_match = re.search(r"MINIMUM CENTRAL PRESSURE\s+-\s+(\d+)\s+MB", text, re.IGNORECASE)
                c_mslp = int(mslp_match.group(1)) if mslp_match else None
                
                mov_match = re.search(r"(\d{3})\s+DEG(?:REES)?\s+AT\s+(\d+)\s+(?:KNOTS|KTS)", text, re.IGNORECASE)
                is_stationary = re.search(r"STATIONARY", text, re.IGNORECASE)

                lat_str = f"{abs(lat)}°{'N' if lat>=0 else 'S'}" if lat else "N/A"
                lon_str = f"{abs(lon)}°{'E' if lon>=0 else 'W'}" if lon else "N/A"
                vmax_str = f"{c_vmax} kt" if c_vmax else "N/A"
                max_vmax_str = f"{max_vmax} kt" if max_vmax else "N/A"

                if mov_match:
                    movement_line = f"\n> **Movement:** {int(mov_match.group(1))}° at {int(mov_match.group(2))} kt"
                elif is_stationary:
                    movement_line = f"\n> **Movement:** Stationary"
                else:
                    movement_line = ""

                pressure_line = f"\n> **Pressure:** {c_mslp} mb" if c_mslp else ""

                wp_storms_map_data.append({
                    "name": storm_name,
                    "run_time": issue_date.strftime("%Y-%m-%d %H:%M UTC"),
                    "is_invest": False,
                    "track": track_points
                })
                
                msg = (f"🔸 **{storm_name}** (Aviation Text)\n"
                       f"> **Position:** {lat_str}, {lon_str}{movement_line}\n"
                       f"> **Intensity:** {vmax_str} (1-min){pressure_line}\n"
                       f"> **Forecast Peak:** {max_vmax_str}\n"
                       f"> **Track Points:** {len(track_points)}")
                wp_official_msgs.append(msg)

        except Exception:
            continue

# --- 3. Save Map Data & Fire Webhook ---
output_data = {"status": "active" if wp_storms_map_data else "inactive", "storms": wp_storms_map_data}
with open("storm_track.json", "w") as f:
    json.dump(output_data, f, indent=4)

if discord_url:
    discord_body = ""
    
    if wp_official_msgs:
        discord_body += "🚨 **Active Western Pacific Storms** 🚨\n" + "\n\n".join(wp_official_msgs) + "\n\n"
    else:
        discord_body += "✅ **No Active Western Pacific Storms**\n\n"
        
    if wp_invest_msgs:
        discord_body += "🔍 **Notable Invests (WP Region)**\n" + "\n\n".join(wp_invest_msgs) + "\n\n"
        
    if global_msgs:
        discord_body += "🌍 **Other Notable Global Storms**\n" + "\n".join(global_msgs)
        
    if wp_official_msgs or wp_invest_msgs or global_msgs:
        requests.post(discord_url, json={"content": discord_body})
