import json,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from pathlib import Path
UA="Mozilla/5.0 (GitHub Actions; QDII dashboard) AppleWebKit/537.36 Chrome/126 Safari/537.36"
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"data.json"
def get(u,h=None):
 r=urllib.request.Request(u,headers={"User-Agent":UA,**(h or {})})
 with urllib.request.urlopen(r,timeout=30) as x:return x.read().decode()
def east(secid):
 q={"fields1":"f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13","fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61","beg":"20260101","end":"20300101","ut":"fa5fd1943c7b386f172d6893dbfba10b","rtntype":"6","secid":secid,"klt":"101","fqt":"0"}
 return "https://push2his.eastmoney.com/api/qt/stock/kline/get?"+urllib.parse.urlencode(q)
def kline(t):
 j=json.loads(t);o=[]
 for s in (j.get("data") or {}).get("klines") or []:
  a=s.split(",")
  if len(a)>=3:
   try:o.append({"t":int(datetime.fromisoformat(a[0]).replace(tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()*1000),"c":float(a[2])})
   except:pass
 return o[-180:]
def nav(code):
 t=get(f"https://fund.eastmoney.com/pingzhongdata/{code}.js?t={int(datetime.now().timestamp()*1000)}",{"Referer":"https://fund.eastmoney.com/"})
 m=re.search(r"var Data_netWorthTrend\s*=\s*(\[.*?\]);",t,re.S)
 if not m:raise RuntimeError("NAV parse")
 o=[]
 for x in json.loads(m.group(1)):
  try:
   d=datetime.fromtimestamp(int(x["x"])/1000,tz=timezone.utc).astimezone(ZoneInfo("Asia/Shanghai"))
   o.append({"date":d.strftime("%Y-%m-%d"),"nav":float(x["y"]),"chg":float(x.get("equityReturn") or 0)})
  except:pass
 return o[-180:]
def yahoo(sym):
 u=f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym,safe='')}?range=6mo&interval=1d&includePrePost=false"
 z=json.loads(get(u))["chart"]["result"][0];o=[]
 for t,c in zip(z.get("timestamp") or [],(z.get("indicators",{}).get("quote",[{}])[0].get("close") or [])):
  if c is not None:o.append({"t":int(t)*1000,"c":float(c)})
 return o[-180:]
def main():
 d={"updatedAt":datetime.now(timezone.utc).isoformat(),"domestic":{"markets":{},"nav":{}},"foreign":{"markets":{},"nav":{}}}
 for k,s in [("N","100.NDX100"),("SP","100.SPX"),("FX","133.USDCNH")]:
  try:d["domestic"]["markets"][k]=kline(get(east(s)))
  except:d["domestic"]["markets"][k]=[]
 for k,c in [("N","016452"),("SP","017641")]:
  try:d["domestic"]["nav"][k]=nav(c)
  except:d["domestic"]["nav"][k]=[]
 for k,s in [("N","^NDX"),("SP","^GSPC"),("FX","USDCNY=X")]:
  try:d["foreign"]["markets"][k]=yahoo(s)
  except:d["foreign"]["markets"][k]=[]
 d["foreign"]["nav"]=d["domestic"]["nav"]
 OUT.write_text(json.dumps(d,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
if __name__=="__main__":main()
