f = open("/home/pi/.node-red/flows.json")
c = f.read()
f.close()
old = 'app.js?v=1.1'
new = 'app.js?v=1.2'
if old in c:
    c = c.replace(old, new)
    f = open("/home/pi/.node-red/flows.json", "w")
    f.write(c)
    f.close()
    print("bumped to 1.2")
else:
    print("already 1.2 or not found")
