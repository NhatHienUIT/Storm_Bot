import os
import re
import json
import requests
import pandas as pd
import sys
from datetime import datetime, timedelta, timezone

discord_url = os.environ.get("DISCORD_WEBHOOK")
wp_storms_data = []
wp_discord_messages = []

# --- METHOD 1: Try the ATCF Data Files ---
directory_url = "https://ftp.nhc.noaa.gov/atcf/aid_public/"
print("1. Checking NOAA ATCF servers...")
try:
    response = requests.get(directory_url, timeout=10)
    official_storms = re.findall(r'href="(a?wp[0-4]\d\d{4}\.dat(?:\.gz)?)"', response.text)
    invests = re.findall(r'href="(a?wp9\d\d{4}\.dat(?:\.gz)?)"', response.text)
    atcf_files = list(set(official_storms + invests))
except:
    atcf_files = []

# (Your existing ATCF parsing logic would go here if files were found. 
# For brevity and to focus on the text fallback, we will assume it failed or skipped.)
# Let's say we checked ATCF and found nothing active, so we flag it to use the text fallback.
atcf_success = len(atcf_files) > 0 

# --- METHOD 2: The Aviation Text Fallback (GTS) ---
if not atcf_success:
    print("2. ATCF files missing or empty. Engaging Aviation Text Fallback...")
    
    urls = [f"https://tgftp.nws.noaa.gov/data/raw/wt/wtpn3{i}.pgtw..txt" for i in range(1, 6)]
    now_utc = datetime.now(timezone.utc)
    
    for url in urls:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code != 200: continue
            text = r.text
            
            # Skip if it's explicitly marked as a dead storm
            if "FINAL WARNING" in text: continue
            
            # Extract Storm Name
            subj_match = re.search(r"SUBJ/(.*?) WARNING", text)
            if not subj_match: continue
            storm_name = subj_match.group(1).strip().title()
            
            # Extract Date/Time to ignore ghost storms (Format: 061800Z)
            time_match = re.search(r"WARNING POSITION:\s+(\d{2})(\d{2})(\d{2})Z", text)
            if not time_match: continue
            
            day, hour = int(time_match.group(1)), int(time_match.group(2))
            
            # Create a rough datetime object to check if this is from the last 48 hours
            # (Assuming current month/year since JTWC resets these slots often)
            try:
                issue_date = now_utc.replace(day=day, hour=hour, minute=0, second=0, microsecond=0)
                # Handle month rollover (e.g. it's the 1st, but the warning was the 31st)
                if issue_date > now_utc + timedelta(days=1): 
                    issue_date = issue_date.replace(month=issue_date.month - 1)
            except:
                continue

            # If the warning is older than 48 hours, it's a dead storm slot. Skip it.
            if now_utc - issue_date > timedelta(hours=48):
                continue
                
            print(f"✅ Active Warning Found: {storm_name}")
            
            # --- Extract Track Coordinates using Regex ---
            track_points = []
            
            def parse_text_coord(lat_str, lon_str):
                lat = float(lat_str[:-1])
                lon = float(lon_str[:-1])
                if lat_str[-1] == 'S': lat = -lat
                if lon_str[-1] == 'W': lon = -lon
                return lat, lon

            # 1. Get Current Position
            pos_match = re.search(r"WARNING POSITION:.*?NEAR\s+(\d+\.\d+[NS])\s+(\d+\.\d+[EW])", text, re.DOTALL)
            if pos_match:
                lat, lon = parse_text_coord(pos_match.group(1), pos_match.group(2))
                track_points.append({"FORECAST_HOUR": 0, "lat": lat, "lon": lon})
                
            # 2. Get Forecast Positions
            forecasts = re.finditer(r"(\d{2})\s+HRS, VALID AT:.*?---\s+(\d+\.\d+[NS])\s+(\d+\.\d+[EW])", text, re.DOTALL)
            for f in forecasts:
                f_hour = int(f.group(1))
                lat, lon = parse_text_coord(f.group(2), f.group(3))
                track_points.append({"FORECAST_HOUR": f_hour, "lat": lat, "lon": lon})
            
            # Save to the JSON payload
            wp_storms_data.append({
                "name": storm_name,
                "run_time": issue_date.strftime("%Y-%m-%d %H:%M UTC"),
                "is_invest": False,
                "track": track_points
            })
            
            wp_discord_messages.append(f"• **{storm_name}**: {len(track_points)} track points (Source: Aviation Text)")

        except Exception as e:
            print(f"Error parsing text warning: {e}")

# --- 3. Save Map Data & Fire Webhook ---
output_data = {"status": "active" if wp_storms_data else "inactive", "storms": wp_storms_data}
with open("storm_track.json", "w") as f:
    json.dump(output_data, f, indent=4)
print(f"Saved {len(wp_storms_data)} active systems to JSON.")

if discord_url and wp_discord_messages:
    joined_msgs = "\n".join(wp_discord_messages)
    message = {
        "content": f"🚨 **Multi-Storm Update** 🚨\nTracking {len(wp_storms_data)} active system(s) in the Western Pacific:\n{joined_msgs}"
    }
    requests.post(discord_url, json=message)
