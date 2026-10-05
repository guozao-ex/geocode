import io, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from gis.client import Client

c = Client()
AOI = {"type":"Polygon","coordinates":[[[116.30,39.95],[116.40,39.95],
                                        [116.40,40.02],[116.30,40.02],[116.30,39.95]]]}

print("1) 设置 spec")
r = c.set_spec({
    "id":"s2_beijing_test", "asset":"COPERNICUS/S2_SR_HARMONIZED",
    "bands":["B4","B3","B2"], "scale":10, "crs":"EPSG:32650",
    "dtype":"uint16", "time_range":["2024-06-01","2024-08-31"],
    "reducer":"median", "aoi":AOI,
})
print("   id   :", r["spec"]["id"])
print("   指纹 :", r["spec"]["fingerprint"])
print("   未知键:", r["unknown_keys"])

print("2) 提交 emit/file")
sub = c.submit(kind="emit", exit="file")
jid = sub["job_id"]
print("   job_id:", jid)

print("3) 跟踪进度")
last = None
for _ in range(80):
    j = c.job(jid)["job"]
    line = f'   [{j["status"]:8s}] {j["pct"]:5.1f}%  {j["phase"]:12s} {j["message"][:58]}'
    if line != last:
        print(line); last = line
    if j["status"] in ("done","failed","cancelled"):
        print()
        if j["status"] == "done":
            res = j.get("result") or {}
            print("   ✅ 产物 :", res.get("path"))
            print("      体积 :", res.get("size_mb"), "MB")
            print("      指纹 :", res.get("spec_fingerprint"))
            print("      栅格 :", res.get("raster"))
        else:
            print("   ❌ 错误 :"); 
            for l in (j.get("error") or "").splitlines()[:14]: print("      "+l)
        break
    time.sleep(3)
