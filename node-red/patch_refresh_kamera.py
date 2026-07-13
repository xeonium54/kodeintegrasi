f = open("/home/pi/kodeintegrasi/static/app.js")
c = f.read()
f.close()

old = '  if (img) img.src = "/monitor/stream/overview.mjpg?size=540p&t=" + Date.now();'
new = '  await fetch("/monitor/record", { method: "POST" }).catch(() => {});\n  if (img) img.src = "/monitor/stream/overview.mjpg?size=540p&t=" + Date.now();\n  if (typeof loadVisionPieces === "function") loadVisionPieces();'

# Check old state: either the old line without any additions
# or update if the record line exists but loadVisionPieces doesn't
if old in c:
    c = c.replace(old, new)
    print("full patch applied")
elif 'await fetch("/monitor/record"' in c and 'loadVisionPieces' not in c:
    # record exists but loadVisionPieces missing: add it after record line
    c = c.replace(
        '  await fetch("/monitor/record", { method: "POST" }).catch(() => {});',
        '  await fetch("/monitor/record", { method: "POST" }).catch(() => {});\n  if (typeof loadVisionPieces === "function") loadVisionPieces();'
    )
    print("added loadVisionPieces")
else:
    print("skipped")

f = open("/home/pi/kodeintegrasi/static/app.js", "w")
f.write(c)
f.close()
