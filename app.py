
import streamlit as st
import pandas as pd
import requests
import re
import time
from datetime import datetime

st.set_page_config(page_title="Testbook YouTube Subscriber Dashboard", page_icon="📊", layout="wide")

st.title("📊 Testbook YouTube Subscriber Dashboard")
st.caption("Multi-channel subscriber monitoring using the official YouTube Data API v3.")

DEFAULT_CSV = "channels.csv"

def extract_identifier(url):
    url = str(url).strip()
    m = re.search(r"youtube\.com/channel/([A-Za-z0-9_-]+)", url)
    if m:
        return ("id", m.group(1))
    m = re.search(r"youtube\.com/@([^/?]+)", url)
    if m:
        return ("handle", "@" + m.group(1))
    m = re.search(r"youtube\.com/user/([^/?]+)", url)
    if m:
        return ("username", m.group(1))
    return (None, None)

@st.cache_data(ttl=300, show_spinner=False)
def fetch_channels(api_key, rows):
    results = []
    errors = []
    session = requests.Session()

    for name, url in rows:
        kind, value = extract_identifier(url)
        if not kind:
            errors.append((name, "Could not read channel URL"))
            continue

        params = {"part": "snippet,statistics", "key": api_key}
        params[kind if kind != "handle" else "forHandle"] = value

        try:
            r = session.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params=params,
                timeout=15
            )
            data = r.json()
            if r.status_code != 200 or not data.get("items"):
                msg = data.get("error", {}).get("message", f"HTTP {r.status_code}")
                errors.append((name, msg))
                continue

            item = data["items"][0]
            stats = item.get("statistics", {})
            subs = None if stats.get("hiddenSubscriberCount") else int(stats.get("subscriberCount", 0))
            results.append({
                "Channel": name,
                "Subscribers": subs,
                "Views": int(stats.get("viewCount", 0)),
                "Videos": int(stats.get("videoCount", 0)),
                "Channel ID": item["id"],
                "URL": url,
                "Fetched At": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception as e:
            errors.append((name, str(e)))

    return pd.DataFrame(results), errors

def fmt(n):
    if pd.isna(n):
        return "Hidden"
    n = int(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return f"{n:,}"

with st.sidebar:
    st.header("⚙️ Settings")
    api_key = st.text_input("YouTube Data API v3 Key", type="password")
    refresh = st.slider("Refresh interval (minutes)", 1, 60, 5)
    st.caption("The official API subscriberCount is rounded by YouTube.")
    st.markdown("[Create/manage API key](https://console.cloud.google.com/apis/credentials)")

if not api_key:
    st.info("Enter your YouTube Data API v3 key in the sidebar to start.")
    st.stop()

try:
    df_input = pd.read_csv(DEFAULT_CSV)
except Exception:
    st.error("channels.csv not found. Keep it in the same folder as app.py.")
    st.stop()

# Allow editing the channel list before fetching
edited = st.data_editor(
    df_input,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "YouTube URL": st.column_config.LinkColumn("YouTube URL"),
    },
    key="channel_editor"
)

rows = list(edited[["Channel Name", "YouTube URL"]].itertuples(index=False, name=None))

if st.button("🔄 Fetch Subscriber Counts Now", type="primary", use_container_width=True):
    fetch_channels.clear()
    st.rerun()

data, errors = fetch_channels(api_key, tuple(rows))

if not data.empty:
    total = int(data["Subscribers"].dropna().sum())
    avg = int(data["Subscribers"].dropna().mean())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Channels Found", len(data))
    c2.metric("Total Subscribers*", fmt(total))
    c3.metric("Average / Channel", fmt(avg))
    c4.metric("Last Refresh", data["Fetched At"].iloc[0].split(" ")[1])

    display = data.copy()
    display["Subscribers"] = display["Subscribers"].apply(fmt)
    display["Views"] = display["Views"].apply(lambda x: f"{x:,}")
    display["Videos"] = display["Videos"].apply(lambda x: f"{x:,}")

    st.subheader("📈 Channel Subscriber Count")
    st.dataframe(
        display[["Channel","Subscribers","Views","Videos","Fetched At","URL"]],
        use_container_width=True,
        hide_index=True,
        column_config={"URL": st.column_config.LinkColumn("YouTube")}
    )

    csv = data.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download Current Report CSV", csv, "youtube_subscribers.csv", "text/csv")

if errors:
    st.warning(f"{len(errors)} channel(s) could not be fetched.")
    with st.expander("Show errors"):
        for name, msg in errors:
            st.write(f"**{name}:** {msg}")

st.caption("*Total is based on the rounded subscriberCount returned by YouTube's official API, not an exact real-time counter.")
st.caption(f"Auto-refresh suggestion: use an external scheduler/Streamlit Cloud setup if you want unattended monitoring every {refresh} minutes.")
