import streamlit as st
import pandas as pd, requests, re, time
from datetime import datetime, timedelta

st.set_page_config(page_title="Testbook YouTube Command Center", page_icon="📊", layout="wide")
st.title("📊 Testbook YouTube Command Center")
st.caption("29-channel subscriber monitoring • YouTube Data API v3 • Persistent Google Sheets history")

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GS_OK=True
except Exception:
    GS_OK=False

def ident(url):
    for p,k,pre in [(r"youtube\.com/channel/([A-Za-z0-9_-]+)","id",""),
                    (r"youtube\.com/@([^/?]+)","forHandle","@"),
                    (r"youtube\.com/user/([^/?]+)","forUsername","")]:
        m=re.search(p,str(url))
        if m:return k,pre+m.group(1)
    return None,None

def fetch(api,rows):
    out=[]; errors=[]; now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for name,url in rows:
        k,v=ident(url)
        if not k: errors.append((name,"Invalid YouTube URL")); continue
        try:
            r=requests.get("https://www.googleapis.com/youtube/v3/channels",
                params={"part":"snippet,statistics","key":api,k:v},timeout=15)
            p=r.json()
            if r.status_code!=200 or not p.get("items"):
                errors.append((name,p.get("error",{}).get("message",f"HTTP {r.status_code}"))); continue
            s=p["items"][0]["statistics"]
            out.append({"Channel":name,"Subscribers":None if s.get("hiddenSubscriberCount") else int(s.get("subscriberCount",0)),
                        "Views":int(s.get("viewCount",0)),"Videos":int(s.get("videoCount",0)),
                        "Channel ID":p["items"][0]["id"],"URL":url,"Fetched At":now})
        except Exception as e: errors.append((name,str(e)))
    return pd.DataFrame(out),errors

def fmt(x):
    if pd.isna(x): return "Hidden"
    x=int(x)
    return f"{x/1e6:.2f}M" if x>=1e6 else f"{x/1e3:.1f}K" if x>=1e3 else f"{x:,}"

@st.cache_resource
def get_ws():
    if not GS_OK or "gcp_service_account" not in st.secrets or "GOOGLE_SHEET_ID" not in st.secrets:return None
    info=dict(st.secrets["gcp_service_account"])
    creds=Credentials.from_service_account_info(info,scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"])
    return gspread.authorize(creds).open_by_key(st.secrets["GOOGLE_SHEET_ID"]).sheet1

def save_rows(ws,d):
    if not ws.get_all_values():
        ws.append_row(["Fetched At","Channel","Subscribers","Views","Videos","Channel ID"],value_input_option="USER_ENTERED")
    ws.append_rows([[r["Fetched At"],r["Channel"],"" if pd.isna(r["Subscribers"]) else int(r["Subscribers"]),
                     int(r["Views"]),int(r["Videos"]),r["Channel ID"]] for _,r in d.iterrows()],
                   value_input_option="USER_ENTERED")

@st.cache_data(ttl=60)
def history():
    empty = pd.DataFrame(columns=[
        "Fetched At", "Channel", "Subscribers", "Views", "Videos", "Channel ID"
    ])
    ws = get_ws()
    if ws is None:
        return empty
    try:
        values = ws.get_all_values()
        if not values:
            return empty

        # Find the expected header row. This avoids KeyError if the sheet has
        # a blank row or any pre-existing content above the dashboard data.
        expected = {"Fetched At", "Channel", "Subscribers", "Views", "Videos", "Channel ID"}
        header_row = None
        for i, row in enumerate(values[:10]):
            if expected.issubset(set(str(x).strip() for x in row)):
                header_row = i
                break

        if header_row is None:
            return empty

        headers = [str(x).strip() for x in values[header_row]]
        rows = values[header_row + 1:]
        if not rows:
            return empty

        # Normalize row widths to header width.
        normalized = [r[:len(headers)] + [""] * max(0, len(headers)-len(r)) for r in rows]
        h = pd.DataFrame(normalized, columns=headers)

        for col in ["Fetched At", "Channel", "Subscribers", "Views", "Videos", "Channel ID"]:
            if col not in h.columns:
                return empty

        h["Fetched At"] = pd.to_datetime(h["Fetched At"], errors="coerce")
        for col in ["Subscribers", "Views", "Videos"]:
            h[col] = pd.to_numeric(h[col], errors="coerce")

        h = h.dropna(subset=["Fetched At", "Channel"]).copy()
        return h
    except Exception:
        # A history database problem should never take down the YouTube dashboard.
        return empty


# ---------- Professional UI ----------
st.markdown("""
<style>
    .block-container {padding-top: 2rem; padding-bottom: 2rem; max-width: 1700px;}
    [data-testid="stSidebar"] {border-right: 1px solid #e5e7eb;}
    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 14px 16px;
        box-shadow: 0 1px 2px rgba(0,0,0,.04);
    }
    [data-testid="stMetricLabel"] {font-size: .78rem;}
    [data-testid="stMetricValue"] {font-size: 1.45rem; font-weight: 650;}
    .hero {
        padding: 6px 0 18px 0;
        border-bottom: 1px solid #e5e7eb;
        margin-bottom: 20px;
    }
    .hero-title {font-size: 1.75rem; font-weight: 700; letter-spacing: -0.02em; margin: 0;}
    .hero-sub {color: #6b7280; margin-top: 5px; font-size: .9rem;}
    .section-title {font-size: 1.12rem; font-weight: 650; margin: 20px 0 10px;}
    .small-note {color:#6b7280; font-size:.8rem;}
    div[data-testid="stDataFrame"] {border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden;}
    div[data-testid="stTabs"] button {font-weight: 600; padding-top: 8px; padding-bottom: 8px;}
    div[data-testid="stButton"] button, div[data-testid="stDownloadButton"] button {border-radius: 8px;}
    .overview-card {padding: 14px 16px; border: 1px solid #e5e7eb; border-radius: 12px; background: #fff; min-height: 115px;}
    .overview-card-title {font-size: .82rem; font-weight: 650; margin-bottom: 8px;}
    .overview-row {font-size: .84rem; padding: 4px 0; border-bottom: 1px solid #f1f5f9;}
    .overview-row:last-child {border-bottom: 0;}
    .muted {color:#6b7280; font-size:.78rem;}
    .status-ok {background:#ecfdf5; color:#047857; border:1px solid #a7f3d0; padding:8px 10px; border-radius:8px; font-size:.82rem;}

    div[data-baseweb="select"] > div {border-radius: 9px;}
    .section-title {margin-top: 28px;}
    .status-warn {background:#fffbeb; color:#92400e; border:1px solid #fde68a; padding:8px 10px; border-radius:8px; font-size:.82rem;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ⚙️ Controls")
    try:
        secret=st.secrets.get("YOUTUBE_API_KEY","")
    except:
        secret=""
    api=secret or st.text_input("YouTube API Key", type="password")
    if secret:
        st.markdown('<div class="status-ok">● YouTube API connected</div>', unsafe_allow_html=True)
    interval=st.selectbox("Auto-refresh", [1,5,10,15,30,60], index=1, format_func=lambda x:f"{x} min")
    refresh=st.button("↻  Refresh now", use_container_width=True)
    try:
        ws_status=get_ws()
        if ws_status is not None:
            st.markdown('<div class="status-ok">● Google Sheets connected</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="status-warn">● Google Sheets not connected</div>', unsafe_allow_html=True)
    except:
        st.markdown('<div class="status-warn">● Google Sheets needs attention</div>', unsafe_allow_html=True)
    st.divider()
    st.caption("Data source")
    st.caption("YouTube Data API v3")
    st.caption("History: Google Sheets")
    st.divider()
    st.caption("Refresh interval applies while the app is active.")

channels=pd.read_csv("channels.csv")
if "data" not in st.session_state: st.session_state.data=pd.DataFrame()
if "last" not in st.session_state: st.session_state.last=0
if "errors" not in st.session_state: st.session_state.errors=[]

if api and (refresh or st.session_state.data.empty or time.time()-st.session_state.last>=interval*60):
    with st.spinner("Updating channel statistics…"):
        d,e=fetch(api,list(channels[["Channel Name","YouTube URL"]].itertuples(index=False,name=None)))
    if not d.empty:
        st.session_state.data=d
        st.session_state.last=time.time()
        st.session_state.errors=e
        try:
            ws=get_ws()
            if ws:
                save_rows(ws,d)
                history.clear()
        except Exception as ex:
            st.session_state.errors.append(("Google Sheets",str(ex)))

data=st.session_state.data.copy()
if data.empty:
    st.markdown('<div class="hero"><div class="hero-title">📊 Testbook YouTube Command Center</div><div class="hero-sub">Multi-channel performance monitoring</div></div>', unsafe_allow_html=True)
    st.info("Connect the YouTube API and click Refresh now.")
    st.stop()

h=history()
if not h.empty:
    prev=h.sort_values("Fetched At").groupby("Channel").nth(-2).reset_index()[["Channel","Subscribers"]].rename(columns={"Subscribers":"Previous"})
    data=data.merge(prev,on="Channel",how="left")
else:
    data["Previous"]=pd.NA

data["Growth"]=data["Subscribers"]-pd.to_numeric(data["Previous"],errors="coerce")
data["Growth %"]=data["Growth"]/data["Previous"]*100
data["Rank"]=data["Subscribers"].rank(method="min",ascending=False).astype("Int64")

# Historical period metrics
periods={"1D":1,"7D":7,"30D":30,"90D":90}
period_growth={}
if not h.empty:
    hs=h.sort_values("Fetched At")
    for label,days in periods.items():
        cutoff=pd.Timestamp.now()-pd.Timedelta(days=days)
        x=hs[hs["Fetched At"]>=cutoff]
        if not x.empty:
            first=x.groupby("Channel",as_index=False).first()[["Channel","Subscribers"]].rename(columns={"Subscribers":"Start"})
            last=x.groupby("Channel",as_index=False).last()[["Channel","Subscribers"]].rename(columns={"Subscribers":"Current"})
            g=first.merge(last,on="Channel")
            g["Growth"]=g["Current"]-g["Start"]
            period_growth[label]=g
        else:
            period_growth[label]=pd.DataFrame()

total_growth=int(pd.to_numeric(data["Growth"],errors="coerce").fillna(0).sum())

st.markdown("""
<div class="hero">
  <div class="hero-title">📊 Testbook YouTube Command Center</div>
  <div class="hero-sub">29-channel performance monitoring · Subscriber growth · Historical analytics</div>
</div>
""", unsafe_allow_html=True)

c1,c2,c3,c4=st.columns(4)
c1.metric("Channels", f"{len(data):,}")
c2.metric("Total subscribers", fmt(data["Subscribers"].sum()))
c3.metric("Since previous fetch", f"{total_growth:+,}")
c4.metric("Last refresh", str(data["Fetched At"].iloc[0]).split()[1] if len(data) else "—")

st.markdown('<div class="section-title">Channel performance</div>', unsafe_allow_html=True)
view_mode=st.radio("View", ["Management", "All channels"], horizontal=True, label_visibility="collapsed")

f1,f2,f3=st.columns([2,1,1])
with f1:
    search=st.text_input("Search channel", placeholder="Type a channel name…", label_visibility="collapsed")
with f2:
    sort=st.selectbox("Sort by", ["Subscribers","Growth","Views","Videos"], label_visibility="collapsed")
with f3:
    order=st.selectbox("Order", ["High → Low","Low → High"], label_visibility="collapsed")

view=data[data["Channel"].str.contains(search,case=False,na=False)].copy() if search else data.copy()
view=view.sort_values(sort,ascending=order=="Low → High",na_position="last")
if view_mode == "Management" and not search:
    view=view.head(10)

show=view.copy()
show["Subscribers"]=show["Subscribers"].apply(fmt)
show["Growth"]=pd.to_numeric(show["Growth"],errors="coerce").apply(lambda x:"—" if pd.isna(x) else f"{int(x):+,}")
show["Growth %"]=pd.to_numeric(show["Growth %"],errors="coerce").apply(lambda x:"—" if pd.isna(x) else f"{x:+.2f}%")
show["Views"]=show["Views"].map(lambda x:f"{int(x):,}")
show["Videos"]=show["Videos"].map(lambda x:f"{int(x):,}")
show["Fetched At"]=show["Fetched At"].astype(str)

st.dataframe(
    show[["Rank","Channel","Subscribers","Growth","Growth %","Views","Videos","Fetched At","URL"]],
    use_container_width=True, hide_index=True, height=430,
    column_config={
        "Rank": st.column_config.NumberColumn("Rank", width="small"),
        "Channel": st.column_config.TextColumn("Channel", width="medium"),
        "Subscribers": st.column_config.TextColumn("Subscribers", width="small"),
        "Growth": st.column_config.TextColumn("Growth", width="small"),
        "Growth %": st.column_config.TextColumn("Growth %", width="small"),
        "Views": st.column_config.TextColumn("Views", width="medium"),
        "Videos": st.column_config.TextColumn("Videos", width="small"),
        "Fetched At": st.column_config.TextColumn("Fetched", width="medium"),
        "URL": st.column_config.LinkColumn("YouTube", display_text="Open channel", width="small"),
    }
)

st.markdown('<div class="section-title">Growth analytics</div>', unsafe_allow_html=True)
g1,g2,g3,g4=st.tabs(["1 Day","7 Days","30 Days","90 Days"])

def render_growth(days, tab):
    with tab:
        g=period_growth.get(days if isinstance(days,str) else str(days), pd.DataFrame())
        if g.empty:
            st.info("More snapshots are needed to calculate this period.")
            return
        g["Growth"]=pd.to_numeric(g["Growth"],errors="coerce").fillna(0)
        up=int(g["Growth"].sum())
        fastest=g.sort_values("Growth",ascending=False).head(10).copy()
        fastest["Start"]=fastest["Start"].apply(fmt)
        fastest["Current"]=fastest["Current"].apply(fmt)
        fastest["Growth"]=fastest["Growth"].apply(lambda x:f"{int(x):+,}")
        a,b=st.columns([1,3])
        a.metric("Net subscriber growth", f"{up:+,}")
        b.dataframe(fastest[["Channel","Start","Current","Growth"]], use_container_width=True, hide_index=True)

render_growth("1D",g1)
render_growth("7D",g2)
render_growth("30D",g3)
render_growth("90D",g4)

st.markdown('<div class="section-title">Subscriber trend</div>', unsafe_allow_html=True)
if not h.empty:
    picks=st.multiselect("Select channels", list(h["Channel"].unique()), default=list(data.sort_values("Subscribers",ascending=False)["Channel"].head(5)), label_visibility="collapsed")
    if picks:
        p=h[h["Channel"].isin(picks)].pivot_table(index="Fetched At",columns="Channel",values="Subscribers",aggfunc="last").sort_index()
        st.line_chart(p, height=330)
else:
    st.info("Subscriber trend will appear after historical snapshots are collected.")


st.markdown('<div class="section-title">Channel deep dive</div>', unsafe_allow_html=True)

detail_channels=list(data.sort_values("Subscribers", ascending=False)["Channel"])
if detail_channels:
    selected=st.selectbox("Select a channel", detail_channels, label_visibility="collapsed")
    current=data[data["Channel"]==selected].iloc[0]

    dc1,dc2,dc3,dc4=st.columns(4)
    dc1.metric("Subscribers", fmt(current["Subscribers"]))
    dc2.metric("Current growth", f'{int(current["Growth"]):+,}' if pd.notna(current["Growth"]) else "—")
    dc3.metric("Total views", f'{int(current["Views"]):,}')
    dc4.metric("Videos", f'{int(current["Videos"]):,}')

    if not h.empty:
        ch=h[h["Channel"]==selected].sort_values("Fetched At").copy()
        if not ch.empty:
            chart=ch.set_index("Fetched At")[["Subscribers"]]
            st.line_chart(chart, height=300)

            latest=ch.iloc[-1]
            first=ch.iloc[0]
            total_growth=int(latest["Subscribers"]-first["Subscribers"]) if pd.notna(latest["Subscribers"]) and pd.notna(first["Subscribers"]) else 0
            st.caption(
                f"Historical snapshots: {len(ch)} · "
                f"First recorded: {first['Fetched At'].strftime('%d %b %Y %H:%M') if pd.notna(first['Fetched At']) else '—'} · "
                f"Total recorded growth: {total_growth:+,}"
            )
        else:
            st.info("No historical snapshots are available for this channel yet.")

st.markdown('<div class="section-title">Management snapshot</div>', unsafe_allow_html=True)

# Compact management summary
if not h.empty:
    latest_ts=pd.to_datetime(h["Fetched At"], errors="coerce").max()
    snapshots=len(h)
    unique_days=h["Fetched At"].dt.date.nunique()

    m1,m2,m3,m4=st.columns(4)
    m1.metric("Snapshots stored", f"{snapshots:,}")
    m2.metric("Snapshot days", f"{unique_days:,}")
    m3.metric("Channels tracked", f"{h['Channel'].nunique():,}")
    m4.metric("Latest data", latest_ts.strftime("%d %b %Y") if pd.notna(latest_ts) else "—")

with st.expander("📥 Reports & data"):
    r1,r2=st.columns(2)
    with r1:
        st.download_button("Download current report", data=data.to_csv(index=False).encode(), file_name="youtube_current_report.csv", mime="text/csv", use_container_width=True)
    with r2:
        if not h.empty:
            st.download_button("Download historical data", data=h.to_csv(index=False).encode(), file_name="youtube_historical_data.csv", mime="text/csv", use_container_width=True)
        else:
            st.caption("Historical export will appear after snapshots are stored.")

if st.session_state.errors:
    with st.expander(f"⚠️ {len(st.session_state.errors)} issue(s)"):
        for n,m in st.session_state.errors:
            st.write(f"**{n}:** {m}")

st.caption("Subscriber counts are provided by YouTube Data API v3 and may be rounded by YouTube. Historical snapshots are stored in Google Sheets.")
st.markdown(f'<meta http-equiv="refresh" content="{interval*60}">',unsafe_allow_html=True)
