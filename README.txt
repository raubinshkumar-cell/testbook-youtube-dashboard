
# Testbook YouTube Subscriber Dashboard

## What it does
- Tracks the 28 YouTube channels supplied by the user.
- Fetches subscriber count, total views, and video count through YouTube Data API v3.
- Refreshes API data every 5 minutes through Streamlit's cache TTL (configurable in the UI).
- Lets you edit/add/remove channel URLs.
- Exports the current result as CSV.

## Important YouTube limitation
The official YouTube Data API `statistics.subscriberCount` is rounded down to three significant figures. This dashboard therefore does **not** claim to provide an exact second-by-second public subscriber counter.

## Setup
1. Install Python 3.10+.
2. Open PowerShell in this folder.
3. Run:
   `pip install -r requirements.txt`
4. Create a Google Cloud project and enable **YouTube Data API v3**.
5. Create an API key.
6. Run:
   `streamlit run app.py`
7. Open the local URL shown by Streamlit.
8. Paste your API key into the sidebar.

## API quota
`channels.list` has a quota cost of 1 unit per call. This app makes one call per channel when refreshing, so 28 channels require roughly 28 quota units per refresh. The default YouTube API quota is 10,000 units/day.

## Files
- `app.py` — dashboard
- `channels.csv` — your 28 channel list
- `requirements.txt` — Python dependencies
