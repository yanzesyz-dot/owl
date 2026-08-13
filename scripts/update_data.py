import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data.json"

EAST_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://quote.eastmoney.com/",
    "Origin": "https://quote.eastmoney.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
YAHOO_HEADERS = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}

def get(url, headers=None, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                body = r.read().decode("utf-8", errors="replace")
            if not body:
                raise RuntimeError("empty response")
            return body
        except Exception as e:
            last = e
            if i + 1 < retries:
                time.sleep(2.5)
    raise last

def eastmoney_kline_url(secid):
    params = {
        "secid": secid,
        "klt": "101",
        "fqt": "0",
        "beg": "20250101",
        "end": "20991231",
        "lmt": "500",
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "_": str(int(time.time() * 1000)),
    }
    return "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urllib.parse.urlencode(params)

def parse_eastmoney(text):
    rows = (json.loads(text).get("data") or {}).get("klines") or []
    out = []
    for row in rows:
        a = row.split(",")
        if len(a) < 9:
            continue
        try:
            dt = datetime.fromisoformat(a[0]).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
            out.append({"t": int(dt.timestamp() * 1000), "c": float(a[2]), "pct": float(a[8])})
        except (ValueError, TypeError):
            continue
    return out[-240:]

def eastmoney(secid):
    return parse_eastmoney(get(eastmoney_kline_url(secid), EAST_HEADERS))

def nav(code):
    url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js?t={int(time.time() * 1000)}"
    text = get(url, {**EAST_HEADERS, "Referer": "https://fund.eastmoney.com/"})
    m = re.search(r"var Data_netWorthTrend\s*=\s*(\[.*?\]);", text, re.S)
    if not m:
        raise RuntimeError("NAV parse failed")
    out = []
    for x in json.loads(m.group(1)):
        try:
            d = datetime.fromtimestamp(int(x["x"]) / 1000, tz=timezone.utc).astimezone(ZoneInfo("Asia/Shanghai"))
            out.append({
                "date": d.strftime("%Y-%m-%d"),
                "nav": float(x["y"]),
                "chg": float(x.get("equityReturn") or 0),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return out[-240:]

def yahoo(symbol):
    params = urllib.parse.urlencode({
        "range": "1y",
        "interval": "1d",
        "includePrePost": "false",
        "events": "div,splits",
    })
    last = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            url = f"https://{host}/v8/finance/chart/{urllib.parse.quote(symbol, safe='')}?{params}"
            j = json.loads(get(url, YAHOO_HEADERS))
            result = (j.get("chart") or {}).get("result") or []
            if not result:
                raise RuntimeError("Yahoo empty result")
            z = result[0]
            closes = ((z.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
            out = [{"t": int(ts) * 1000, "c": float(c)}
                   for ts, c in zip(z.get("timestamp") or [], closes) if c is not None]
            if out:
                return out[-240:]
            raise RuntimeError("Yahoo no close data")
        except Exception as e:
            last = e
    raise last

def load_existing():
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {}

def main():
    old = load_existing()
    d = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "domestic": {"markets": {}, "nav": {}},
        "foreign": {"markets": {}, "nav": {}},
        "errors": {},
    }

    # Domestic: Eastmoney. N is NASDAQ-100, not NASDAQ Composite.
    for k, secid in {"N": "100.NDX100", "SP": "100.SPX", "FX": "133.USDCNH"}.items():
        try:
            rows = eastmoney(secid)
            if not rows:
                raise RuntimeError("Eastmoney returned no rows")
            d["domestic"]["markets"][k] = rows
        except Exception as e:
            d["domestic"]["markets"][k] = (old.get("domestic", {}).get("markets", {}) or {}).get(k, [])
            d["errors"][f"domestic.{k}"] = str(e)

    for k, code in {"N": "016452", "SP": "017641"}.items():
        try:
            d["domestic"]["nav"][k] = nav(code)
        except Exception as e:
            d["domestic"]["nav"][k] = (old.get("domestic", {}).get("nav", {}) or {}).get(k, [])
            d["errors"][f"nav.{k}"] = str(e)

    # Foreign: Yahoo Finance with query2 fallback.
    for k, symbol in {"N": "^NDX", "SP": "^GSPC", "FX": "USDCNY=X"}.items():
        try:
            rows = yahoo(symbol)
            if not rows:
                raise RuntimeError("Yahoo returned no rows")
            d["foreign"]["markets"][k] = rows
        except Exception as e:
            d["foreign"]["markets"][k] = (old.get("foreign", {}).get("markets", {}) or {}).get(k, [])
            d["errors"][f"foreign.{k}"] = str(e)

    d["foreign"]["nav"] = d["domestic"]["nav"]
    OUT.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

if __name__ == "__main__":
    main()
