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

with st.sidebar:
    st.header("⚙️ Controls")
    try: secret=st.secrets.get("YOUTUBE_API_KEY","")
    except: secret=""
    api=secret or st.text_input("YouTube API Key",type="password")
    st.success("YouTube API connected") if secret else None
    interval=st.selectbox("Auto-refresh",[1,5,10,15,30,60],index=1)
    refresh=st.button("🔄 Refresh Now",use_container_width=True)
    try:
        ws_status = get_ws()
        if ws_status is not None:
            st.success("📚 Google Sheets connected")
        else:
            st.warning("📚 Google Sheets not connected")
    except Exception:
        st.warning("📚 Google Sheets needs attention")

channels=pd.read_csv("channels.csv")
if "data" not in st.session_state:st.session_state.data=pd.DataFrame()
if "last" not in st.session_state:st.session_state.last=0
if "errors" not in st.session_state:st.session_state.errors=[]

if api and (refresh or st.session_state.data.empty or time.time()-st.session_state.last>=interval*60):
    with st.spinner("Fetching YouTube statistics…"):
        d,e=fetch(api,list(channels[["Channel Name","YouTube URL"]].itertuples(index=False,name=None)))
    if not d.empty:
        st.session_state.data=d;st.session_state.last=time.time();st.session_state.errors=e
        try:
            ws=get_ws()
            if ws:
                save_rows(ws,d)
                history.clear()
        except Exception as ex:
            st.session_state.errors.append(("Google Sheets",str(ex)))

data=st.session_state.data.copy()
if data.empty:
    st.info("Connect the API and click Refresh Now.");st.stop()

h=history()
if not h.empty:
    prev=h.sort_values("Fetched At").groupby("Channel").nth(-2).reset_index()[["Channel","Subscribers"]].rename(columns={"Subscribers":"Previous"})
    data=data.merge(prev,on="Channel",how="left")
else:data["Previous"]=pd.NA
data["Growth"]=data["Subscribers"]-pd.to_numeric(data["Previous"],errors="coerce")
data["Growth %"]=data["Growth"]/data["Previous"]*100
data["Rank"]=data["Subscribers"].rank(method="min",ascending=False).astype("Int64")

c1,c2,c3,c4=st.columns(4)
c1.metric("📺 Channels",len(data));c2.metric("👥 Total Subscribers",fmt(data["Subscribers"].sum()))
c3.metric("📈 Since Previous Fetch",f"{int(pd.to_numeric(data['Growth'],errors='coerce').fillna(0).sum()):+,}")
c4.metric("🕐 Last Refresh",str(data["Fetched At"].iloc[0]).split()[1])

a,b,c=st.columns([2,1,1])
with a:search=st.text_input("🔎 Search channel")
with b:sort=st.selectbox("Sort by",["Subscribers","Growth","Views","Videos","Rank"])
with c:order=st.selectbox("Order",["High → Low","Low → High"])
view=data[data["Channel"].str.contains(search,case=False,na=False)].copy() if search else data.copy()
view=view.sort_values(sort,ascending=order=="Low → High",na_position="last")

st.subheader("🏆 Channel Ranking")
show=view.copy()
show["Subscribers"]=show["Subscribers"].apply(fmt)
show["Growth"]=pd.to_numeric(show["Growth"],errors="coerce").apply(lambda x:"—" if pd.isna(x) else f"{int(x):+,}")
show["Growth %"]=pd.to_numeric(show["Growth %"],errors="coerce").apply(lambda x:"—" if pd.isna(x) else f"{x:+.2f}%")
show["Views"]=show["Views"].map(lambda x:f"{int(x):,}");show["Videos"]=show["Videos"].map(lambda x:f"{int(x):,}")
st.dataframe(show[["Rank","Channel","Subscribers","Growth","Growth %","Views","Videos","Fetched At","URL"]],
use_container_width=True,hide_index=True,column_config={"URL":st.column_config.LinkColumn("YouTube")})

st.subheader("📅 Historical Growth")
tabs=st.tabs(["7 Days","30 Days","90 Days"])
for tab,days in zip(tabs,[7,30,90]):
    with tab:
        if h.empty:st.info("History will appear after Google Sheets is connected and snapshots are collected.")
        else:
            cutoff=datetime.now()-timedelta(days=days);x=h[h["Fetched At"]>=cutoff]
            if x.empty:st.info("No history in this period yet.")
            else:
                first=x.sort_values("Fetched At").groupby("Channel").first().reset_index()
                last=x.sort_values("Fetched At").groupby("Channel").last().reset_index()
                g=first[["Channel","Subscribers"]].rename(columns={"Subscribers":"Start"}).merge(
                    last[["Channel","Subscribers"]].rename(columns={"Subscribers":"Current"}),on="Channel")
                g["Growth"]=g["Current"]-g["Start"];g=g.sort_values("Growth",ascending=False)
                z=g.copy();z["Start"]=z["Start"].apply(fmt);z["Current"]=z["Current"].apply(fmt);z["Growth"]=z["Growth"].apply(lambda x:f"{int(x):+,}")
                st.dataframe(z[["Channel","Start","Current","Growth"]],use_container_width=True,hide_index=True)

if not h.empty:
    st.subheader("📈 Subscriber History")
    picks=st.multiselect("Channels to plot",list(h["Channel"].unique()),default=list(h["Channel"].unique())[:5])
    if picks:
        p=h[h["Channel"].isin(picks)].pivot_table(index="Fetched At",columns="Channel",values="Subscribers",aggfunc="last").sort_index()
        st.line_chart(p)

st.subheader("📥 Export")
st.download_button("Download Current Report CSV", data.to_csv(index=False).encode(), file_name="youtube_current_report.csv", mime="text/csv")
if not h.empty:st.download_button("Download Full Historical CSV", data=h.to_csv(index=False).encode(), file_name="youtube_historical_data.csv", mime="text/csv")

if st.session_state.errors:
    with st.expander(f"⚠️ {len(st.session_state.errors)} error(s)"):
        for n,m in st.session_state.errors:st.write(f"**{n}:** {m}")

st.caption("YouTube rounds subscriberCount to three significant figures. Historical analytics are stored in Google Sheets.")
st.markdown(f'<meta http-equiv="refresh" content="{interval*60}">',unsafe_allow_html=True)
