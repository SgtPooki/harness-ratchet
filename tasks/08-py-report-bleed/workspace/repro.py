from reportlib import build_report

r1 = build_report("january", [("jan-a", ["alpha,10", "beta,20"])])
r2 = build_report("february", [("feb-a", ["gamma,5"])])

print("january rows:", [r["name"] for r in r1["rows"]], "total", r1["total"])
print("february rows:", [r["name"] for r in r2["rows"]], "total", r2["total"])

assert [r["name"] for r in r2["rows"]] == ["gamma"], "BUG: february contains january rows!"
print("ok")
