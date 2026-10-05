import io, sys, time, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from gis.client import Client
c = Client()
AOI = {"type":"Polygon","coordinates":[[[116.30,39.95],[116.40,39.95],
                                        [116.40,40.02],[116.30,40.02],[116.30,39.95]]]}
c.set_spec({"id":"s2_beijing_test","asset":"COPERNICUS/S2_SR_HARMONIZED",
    "bands":["B4","B3","B2"],"scale":10,"crs":"EPSG:32650","dtype":"uint16",
    "time_range":["2024-06-01","2024-08-31"],"reducer":"median","aoi":AOI,
    "render":{"bands":["B4","B3","B2"],"stretch":"percentile","percentile":[2,98]}})
print("指纹:", c.spec()["spec"]["fingerprint"], "\n")
res = {}
for ex in ("file","array","map"):
    jid = c.submit(kind="emit", exit=ex)["job_id"]
    for _ in range(140):
        j = c.job(jid)["job"]
        if j["status"] in ("done","failed","cancelled"):
            print(f"{ex:6s} {j['status']:8s} {j['elapsed']:6.1f}s  {j['message'][:50]}")
            if j["status"]=="done": res[ex]=j.get("result") or {}
            else:
                for l in (j.get("error") or "").splitlines()[:4]: print("        "+l)
            break
        time.sleep(3)
print("\n" + "="*76)
for ex,r in res.items():
    print(f"{ex}: 指纹={r.get('spec_fingerprint')} 网格={r['grid']['width']}x{r['grid']['height']}")
    for k in ("qgz_error","png_error","grid_problems"):
        if r.get(k): print(f"    {k}: {str(r[k])[:180]}")
    for k in ("qgz","png","path"):
        if r.get(k): print(f"    {k}: {r[k]}")
