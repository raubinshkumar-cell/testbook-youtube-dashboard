import streamlit as st
import pandas as pd, requests, re, time
from datetime import datetime

st.set_page_config(page_title="Testbook YouTube Command Center", page_icon="📊", layout="wide")
st.title("📊 Testbook YouTube Command Center")
st.caption("29-channel subscriber monitoring • YouTube Data API v3")

def ident(url):
    for pattern, key, prefix in [
        (r"youtube\.com/channel/([A-Za-z0-9_-]+)","id",""),
        (r"youtube\.com/@([^/?]+)","forHandle","@"),
        (r"youtube\.com/user/([^/?]+)","forUsername","")]:
        m=re.search(pattern,str(url))
        if m: return key,prefix+m.group(1)
    return None,None

def fetch(api, rows):
    out=[]; errors=[]; now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for name,url in rows:
        key,val=ident(url)
        if not key: errors.append((name,"Invalid URL")); continue
        try:
            r=requests.get("https://www.googleapis.com/youtube/v3/channels",
                params={"part":"snippet,statistics","key":api,key:val},timeout=15)
            p=r.json()
            if r.status_code!=200 or not p.get("items"):
                errors.append((name,p.get("error",{}).get("message",f"HTTP {r.status_code}"))); continue
            s=p["items"][0].get("statistics",{})
            out.append({"Channel":name,"Subscribers":None if s.get("hiddenSubscriberCount") else int(s.get("subscriberCount",0)),
                "Views":int(s.get("viewCount",0)),"Videos":int(s.get("videoCount",0)),
                "URL":url,"Fetched At":now})
        except Exception as e: errors.append((name,str(e)))
    return pd.DataFrame(out),errors

def fmt(x):
    if pd.isna(x): return "Hidden"
    x=int(x)
    return f"{x/1e6:.2f}M" if x>=1e6 else f"{x/1e3:.1f}K" if x>=1e3 else f"{x:,}"

if "data" not in st.session_state: st.session_state.data=pd.DataFrame()
if "history" not in st.session_state: st.session_state.history=pd.DataFrame(columns=["Channel","Subscribers","Fetched At"])
if "last" not in st.session_state: st.session_state.last=0

with st.sidebar:
    st.header("⚙️ Controls")
    try: secret=st.secrets.get("YOUTUBE_API_KEY","")
    except: secret=""
    api=secret or st.text_input("YouTube API Key",type="password")
    if secret: st.success("API connected")
    minutes=st.selectbox("Auto-refresh", [1,5,10,15,30,60], index=1)
    refresh=st.button("🔄 Refresh Now",use_container_width=True)
    if st.button("🗑️ Clear Session History",use_container_width=True):
        st.session_state.history=pd.DataFrame(columns=["Channel","Subscribers","Fetched At"])
        st.session_state.last=0
        st.rerun()

channels=pd.read_csv("channels.csv")
due=time.time()-st.session_state.last >= minutes*60
if api and (refresh or st.session_state.data.empty or due):
    with st.spinner("Fetching YouTube statistics…"):
        new,errors=fetch(api,list(channels[["Channel Name","YouTube URL"]].itertuples(index=False,name=None)))
    if not new.empty:
        st.session_state.data=new
        st.session_state.history=pd.concat([st.session_state.history,new[["Channel","Subscribers","Fetched At"]]],ignore_index=True)
        st.session_state.last=time.time()
        st.session_state.errors=errors

data=st.session_state.data.copy()
if data.empty:
    st.info("Add your API key in the sidebar, then click Refresh Now.")
    st.stop()

hist=st.session_state.history.copy()
if len(hist)>1:
    h=hist.copy(); h["Fetched At"]=pd.to_datetime(h["Fetched At"]); h=h.sort_values("Fetched At")
    prev=h.groupby("Channel").nth(-2).reset_index()[["Channel","Subscribers"]].rename(columns={"Subscribers":"Previous"})
    data=data.merge(prev,on="Channel",how="left")
else: data["Previous"]=pd.NA
data["Growth"]=data["Subscribers"]-pd.to_numeric(data["Previous"],errors="coerce")
data["Growth %"]=data["Growth"]/data["Previous"]*100
data["Rank"]=data["Subscribers"].rank(method="min",ascending=False).astype("Int64")

c1,c2,c3,c4=st.columns(4)
c1.metric("📺 Channels",len(data))
c2.metric("👥 Total Subscribers",fmt(data["Subscribers"].sum()))
c3.metric("📈 Since Previous Fetch",f"{int(pd.to_numeric(data['Growth'],errors='coerce').fillna(0).sum()):+,}")
c4.metric("🕐 Last Refresh",str(data["Fetched At"].iloc[0]).split()[1])

a,b,c=st.columns([2,1,1])
with a: search=st.text_input("🔎 Search channel")
with b: sort=st.selectbox("Sort by",["Subscribers","Growth","Views","Videos","Rank"])
with c: order=st.selectbox("Order",["High → Low","Low → High"])
view=data[data["Channel"].str.contains(search,case=False,na=False)] if search else data.copy()
view=view.sort_values(sort,ascending=(order=="Low → High"),na_position="last")

st.subheader("🏆 Channel Ranking")
show=view.copy()
show["Subscribers"]=show["Subscribers"].apply(fmt)
show["Growth"]=pd.to_numeric(show["Growth"],errors="coerce").apply(lambda x:"—" if pd.isna(x) else f"{int(x):+,}")
show["Growth %"]=pd.to_numeric(show["Growth %"],errors="coerce").apply(lambda x:"—" if pd.isna(x) else f"{x:+.2f}%")
show["Views"]=show["Views"].map(lambda x:f"{int(x):,}")
show["Videos"]=show["Videos"].map(lambda x:f"{int(x):,}")
st.dataframe(show[["Rank","Channel","Subscribers","Growth","Growth %","Views","Videos","Fetched At","URL"]],
    use_container_width=True,hide_index=True,column_config={"URL":st.column_config.LinkColumn("YouTube")})

st.subheader("📊 Subscriber Distribution")
st.bar_chart(view[["Channel","Subscribers"]].dropna().set_index("Channel"))

if len(hist)>1:
    st.subheader("📈 Session Growth")
    h=hist.copy(); h["Fetched At"]=pd.to_datetime(h["Fetched At"])
    pivot=h.pivot_table(index="Fetched At",columns="Channel",values="Subscribers",aggfunc="last").sort_index()
    picks=st.multiselect("Channels to plot",list(pivot.columns),default=list(pivot.columns[:5]))
    if picks: st.line_chart(pivot[picks])

st.subheader("📥 Export")
st.download_button("Download Current Report CSV",data.to_csv(index=False).encode(),"youtube_current_report.csv","text/csv")
st.download_button("Download Session History CSV",hist.to_csv(index=False).encode(),"youtube_session_history.csv","text/csv")

st.caption("YouTube rounds subscriberCount to three significant figures. History in this version lasts for the current app session.")
st.markdown(f'<meta http-equiv="refresh" content="{minutes*60}">',unsafe_allow_html=True)
