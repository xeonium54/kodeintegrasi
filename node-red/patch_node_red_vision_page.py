import json
import pathlib
import re
import shutil
import time


FLOW_PATH = pathlib.Path("/home/pi/.node-red/flows.json")
TEMPLATE_ID = "416f6cdc6cbf9543"
STREAM_URL = "http://10.6.101.123:8000/monitor/stream/overview.mjpg"
PIECES_URL = "http://10.6.101.123:8000/monitor/pieces"
TRACKING_URL = "http://10.6.101.60:8001/monitor/live-tracking"


def remove_old_global_card(template: str) -> str:
    return re.sub(
        r"\n\s*<!-- ponytail: laptop keeps CV; RevPi only embeds the existing MJPEG monitor stream\. -->\s*\n"
        r"\s*<div id=\"visionMonitorCard\"[\s\S]*?</div>\s*\n",
        "\n",
        template,
        count=1,
    )


def remove_existing_vision_page(template: str) -> str:
    template = re.sub(
        r"\n\s*<style>[\s\S]*?#visionPage\.active[\s\S]*?</style>\s*\n",
        "\n",
        template,
    )

    while True:
        start = template.find("<script")
        removed = False
        while start != -1:
            end = template.find("</script>", start)
            if end == -1:
                break
            end += len("</script>")
            block = template[start:end]
            if "visionPollId" in block or "loadVisionPieces" in block:
                template = template[:start] + template[end:]
                removed = True
                break
            start = template.find("<script", end)
        if not removed:
            break

    while True:
        page_idx = template.find('<div id="visionPage"')
        if page_idx == -1:
            break
        next_idx = -1
        for marker in ('<script', '    <footer class="footer-info"', '<footer', '</body>'):
            idx = template.find(marker, page_idx)
            if idx != -1 and (next_idx == -1 or idx < next_idx):
                next_idx = idx
        if next_idx == -1:
            break
        template = template[:page_idx] + template[next_idx:]

    return re.sub(
        r"\n(?:\s*<div style=\"height:18px;grid-column:1/-1\"></div>\s*\n)?"
        r"\s*<div class=\"menu-box\"[^>]*(?:showPage\('visionPage'\)|openVisionPage\(\))[\s\S]*?</div>\s*\n",
        "\n",
        template,
        count=1,
    )


def add_menu_button(template: str) -> str:
    if "openVisionPage()" in template:
        return template
    signout = re.search(r'\n\s*<div class="menu-box"[^>]*onclick="logout\(\)"', template)
    if not signout:
        raise RuntimeError("choicePage signout menu-box not found")

    button = '''
          <div style="height:18px;grid-column:1/-1"></div>
          <div class="menu-box" style="grid-column:1/-1" onclick="openVisionPage()">◉ <span>Live Vision Monitor</span></div>
'''
    return template[:signout.start()] + button + template[signout.start():]


def add_vision_page(template: str) -> str:
    marker = '    <script>'
    if marker not in template:
        marker = '</body>'
    if marker not in template:
        raise RuntimeError("page insert marker not found")

    page = f'''

    <style>
      #visionPage.active {{ display:flex; align-items:center; justify-content:center; min-height:100vh; padding:16px; box-sizing:border-box; }}
    </style>
    <div id="visionPage" class="page">
      <div class="card" style="width:min(94vw,1100px);padding:clamp(14px,3vw,24px);">
        <h2 style="margin-bottom:10px;">Live Vision Monitor</h2>
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin:0 0 12px;">
          <button class="btn btn-back" style="width:100%;" onclick="closeVisionPage()">Kembali</button>
        </div>
        <!-- ponytail: stream cuma hidup saat page ini dibuka. -->
        <img id="visionStream" data-src="{STREAM_URL}?size=540p" alt="Tangram preprocessed vision stream" style="display:block;width:100%;height:auto;max-height:62vh;object-fit:contain;border-radius:18px;background:#111;box-shadow:0 10px 28px rgba(0,0,0,.18);" />
        <div style="overflow:auto;margin-top:14px;">
          <table style="width:100%;border-collapse:collapse;background:rgba(255,255,255,.7);border-radius:12px;overflow:hidden;">
            <thead><tr><th style="padding:8px;text-align:left;">balok</th><th style="padding:8px;text-align:left;">lokasi</th><th style="padding:8px;text-align:left;">x</th><th style="padding:8px;text-align:left;">y</th><th style="padding:8px;text-align:left;">r</th></tr></thead>
            <tbody id="visionPieceRows"><tr><td colspan="5" style="padding:8px;">Belum ada data</td></tr></tbody>
          </table>
        </div>
        <p id="visionTableStatus" style="margin:8px 0 0;font-size:.9em;color:#666;">Tabel aktif saat page ini dibuka.</p>
      </div>
    </div>
    <script>
      var visionPollId = null;
      var visionStreamUrl = "{STREAM_URL}?size=540p";
      var visionPiecesUrl = "{TRACKING_URL}.js";
      function visionNum(value) {{ return typeof value === "number" && !isNaN(value) ? value.toFixed(1) : "-"; }}
      function visionCell(row, text) {{
        var td = document.createElement("td");
        td.style.padding = "8px";
        td.textContent = text;
        row.appendChild(td);
      }}
      function setVisionStatus(text) {{
        var status = document.getElementById("visionTableStatus");
        if (status) status.textContent = text;
      }}
      function renderVisionPieces(data) {{
        var body = document.getElementById("visionPieceRows");
        if (!body) return;
        var pieces = data.pieces || [];
        var rows = pieces.length ? pieces : (data.rigid_objects || []);
        body.innerHTML = "";
        if (!rows.length) {{
          body.innerHTML = '<tr><td colspan="5" style="padding:8px;">API OK, belum ada piece terdeteksi</td></tr>';
          setVisionStatus("API OK, 0 data");
          return;
        }}
        for (var i = 0; i < rows.length; i += 1) {{
          var piece = rows[i] || {{}};
          var pose = piece.pose || {{}};
          var tr = document.createElement("tr");
          visionCell(tr, piece.block_name || piece.piece_id || piece.object_id || piece.shape || "-");
          visionCell(tr, piece.status || piece.zone_name || piece.location || "-");
          visionCell(tr, visionNum(typeof piece.current_x === "number" ? piece.current_x : (typeof pose.x_mm === "number" ? pose.x_mm : piece.x)));
          visionCell(tr, visionNum(typeof piece.current_y === "number" ? piece.current_y : (typeof pose.y_mm === "number" ? pose.y_mm : piece.y)));
          visionCell(tr, visionNum(typeof piece.current_r === "number" ? piece.current_r : (typeof pose.theta_deg === "number" ? pose.theta_deg : piece.theta)));
          body.appendChild(tr);
        }}
        setVisionStatus("Data masuk: " + rows.length + " row");
      }}
      function loadVisionPieces() {{
        var old = document.getElementById("visionPiecesJsonp");
        if (old && old.parentNode) old.parentNode.removeChild(old);
        var script = document.createElement("script");
        script.id = "visionPiecesJsonp";
        script.src = visionPiecesUrl + "?callback=renderVisionPieces&t=" + Date.now();
        script.onerror = function () {{
          var body = document.getElementById("visionPieceRows");
          if (body) body.innerHTML = '<tr><td colspan="5" style="padding:8px;">Data monitor belum siap</td></tr>';
          setVisionStatus("Gagal baca data monitor");
        }};
        document.body.appendChild(script);
      }}
      function openVisionPage() {{
        showPage("visionPage");
        var img = document.getElementById("visionStream");
        if (img && !img.getAttribute("src")) img.src = visionStreamUrl + "&t=" + Date.now();
        loadVisionPieces();
        if (!visionPollId) visionPollId = setInterval(loadVisionPieces, 1500);
      }}
      function closeVisionPage() {{
        var img = document.getElementById("visionStream");
        if (img) img.removeAttribute("src");
        if (visionPollId) clearInterval(visionPollId);
        visionPollId = null;
        showPage("choicePage");
      }}
      document.addEventListener("visibilitychange", function () {{ if (document.hidden && visionPollId) closeVisionPage(); }});
    </script>
'''
    return template.replace(marker, page + "\n" + marker, 1)


backup = FLOW_PATH.with_name(f"flows.json.backup-vision-page-{time.strftime('%Y%m%d-%H%M%S')}")
shutil.copy2(FLOW_PATH, backup)
nodes = json.loads(FLOW_PATH.read_text())
patched = 0

for node in nodes:
    if node.get("id") != TEMPLATE_ID:
        continue
    template = node.get("template", "")
    updated = add_vision_page(add_menu_button(remove_existing_vision_page(remove_old_global_card(template))))
    if updated != template:
        node["template"] = updated
        patched += 1

FLOW_PATH.write_text(json.dumps(nodes, ensure_ascii=False, indent=2))
print(f"backup {backup}")
print(f"patched {patched}")
