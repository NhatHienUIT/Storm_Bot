<div align="center">

# 🌀 Storm Bot SEA

**An automated, highly-resilient tropical cyclone tracking system tailored for the Western Pacific basin.**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg?logo=python&logoColor=white)](#)
[![GitHub Actions](https://img.shields.io/badge/Automated-GitHub%20Actions-2088FF.svg?logo=github-actions&logoColor=white)](#)
[![Leaflet](https://img.shields.io/badge/Mapping-Leaflet.js-99cc33.svg?logo=leaflet&logoColor=white)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#)

</div>

---

## 📖 Overview
**Storm Bot SEA** aggregates raw meteorological data, visualizes forecast tracks on an interactive web map, and pushes real-time intelligence briefings directly to Discord. 

Built for resilience, the system is engineered to bypass government server outages and military geo-blocking by utilizing automated hybrid-fallback parsing and remote execution via GitHub Actions.

---

## ✨ Key Features

* 📡 **Multi-Source Redundancy:** Prioritizes NOAA/JTWC ATCF data files (`.dat`) and automatically falls back to scraping NWS Aviation Text Bulletins (GTS) if primary servers drop the data.
* 🧠 **Smart Data Filtering:** Implements a 48-hour expiration rule to ignore dissipated systems and dynamically formats vague depression designations (e.g., converting "ONE" to "Tropical Depression One").
* 🗺️ **Interactive Web Dashboard:** Uses Leaflet.js to map simultaneous active storm tracks, color-coded for official systems (Red) and developing Invests (Orange). Cache-busting ensures users always see the latest data.
* 💬 **Discord Integration:** Delivers formatted alerts containing real-time coordinates, movement speed/heading, 1-minute sustained winds, central pressure, and forecast peaks.
* 🌍 **Global Radar:** Provides deep-dive analytics for the Western Pacific while maintaining a consolidated summary of other notable global cyclones.

---

## ⚙️ System Architecture

| Component | Description |
| :--- | :--- |
| `fetch_track.py` | The core Python engine. Handles data scraping, multi-line regex parsing across line breaks, coordinate extraction, and JSON payload generation. |
| `index.html` | The lightweight frontend dashboard. Reads the dynamically generated JSON to plot coordinates and display storm telemetry. |
| `update_data.yml` | The GitHub Actions workflow. Automates the pipeline, scheduling the bot to run every 4 hours without manual intervention. |

---

## 🚀 Setup & Deployment

### 1. Clone & Configure
Fork or clone this repository to your own GitHub account.

### 2. Connect Discord Webhooks
Navigate to your repository's **Settings > Secrets and variables > Actions**. 
* Create a new repository secret named `DISCORD_WEBHOOK`.
* Paste your Discord channel's webhook URL.

### 3. Enable Web Hosting
Go to **Settings > Pages** and set the source to deploy from your `main` branch. This will host your `index.html` map via GitHub Pages.

### 4. Initialize the Bot
Go to the **Actions** tab, select the *Fetch Latest Storm Data* workflow, and click **Run workflow** to perform the initial data sync. The system will now run automatically on schedule.

---
<div align="center">
<i>Built with Python, Regex, and a lot of patience for government FTP servers.</i>
</div>
