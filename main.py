from flask import Flask, Response, render_template_string, url_for, jsonify
from collage import generate_collage_png

app = Flask(__name__)

INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Silver Members Collage</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {
      color-scheme: light dark;
    }

    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      padding: 2rem;
      line-height: 1.5;
    }

    .wrap {
      max-width: 1200px;
      margin: 0 auto;
    }

    h1 {
      margin-top: 0;
      margin-bottom: 0.5rem;
      font-size: 1.8rem;
    }

    p {
      margin-top: 0;
    }

    .status {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin: 1rem 0 1.5rem 0;
      font-size: 1rem;
    }

    .spinner {
      width: 18px;
      height: 18px;
      border: 3px solid currentColor;
      border-right-color: transparent;
      border-radius: 50%;
      animation: spin 0.9s linear infinite;
      flex: 0 0 auto;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .hint {
      opacity: 0.75;
      font-size: 0.95rem;
      margin-bottom: 1rem;
    }

    .image-box {
      min-height: 160px;
      border: 1px solid rgba(127,127,127,0.3);
      border-radius: 12px;
      padding: 1rem;
      overflow: auto;
    }

    img {
      max-width: 100%;
      height: auto;
      display: none;
    }

    .error {
      color: #b00020;
      font-weight: 600;
    }

    .actions {
      margin-top: 1rem;
    }

    button {
      font: inherit;
      padding: 0.6rem 0.9rem;
      border-radius: 10px;
      border: 1px solid rgba(127,127,127,0.4);
      background: transparent;
      cursor: pointer;
    }

    button:hover {
      opacity: 0.9;
    }

    .hidden {
      display: none;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Silver Members Collage</h1>
    <p>This page generates the latest collage on demand.</p>

    <div id="status" class="status">
      <div id="spinner" class="spinner" aria-hidden="true"></div>
      <div id="status-text">Starting image generation…</div>
    </div>

    <div class="hint">
      This can take a little while because the service fetches the member page, downloads logos, and renders the PNG.
    </div>

    <div class="image-box">
      <img id="result-image" alt="Silver members collage">
      <div id="fallback-text">Waiting for the image…</div>
    </div>

    <div class="actions hidden" id="actions">
      <button id="reload-btn" type="button">Generate again</button>
    </div>
  </div>

  <script>
    const statusText = document.getElementById("status-text");
    const spinner = document.getElementById("spinner");
    const img = document.getElementById("result-image");
    const fallbackText = document.getElementById("fallback-text");
    const actions = document.getElementById("actions");
    const reloadBtn = document.getElementById("reload-btn");

    let progressTimer = null;
    let slowTimer = null;
    let verySlowTimer = null;

    function resetTimers() {
      if (progressTimer) clearInterval(progressTimer);
      if (slowTimer) clearTimeout(slowTimer);
      if (verySlowTimer) clearTimeout(verySlowTimer);
    }

    function startLoading() {
      resetTimers();

      img.style.display = "none";
      img.removeAttribute("src");
      fallbackText.textContent = "Waiting for the image…";
      fallbackText.classList.remove("error");
      actions.classList.add("hidden");
      spinner.style.display = "block";
      statusText.textContent = "Starting image generation…";

      const messages = [
        "Fetching member list…",
        "Downloading logos…",
        "Normalizing logo sizes…",
        "Rendering collage…"
      ];

      let idx = 0;
      progressTimer = setInterval(() => {
        if (idx < messages.length) {
          statusText.textContent = messages[idx];
          idx += 1;
        }
      }, 1800);

      slowTimer = setTimeout(() => {
        statusText.textContent = "Still working… this is taking a bit longer than usual.";
      }, 9000);

      verySlowTimer = setTimeout(() => {
        statusText.textContent = "Still generating the PNG… please keep this page open.";
      }, 20000);

      const imageUrl = "{{ url_for('silver_members_png') }}?t=" + Date.now();
      img.src = imageUrl;
    }

    img.onload = () => {
      resetTimers();
      spinner.style.display = "none";
      statusText.textContent = "Done.";
      fallbackText.textContent = "";
      img.style.display = "block";
      actions.classList.remove("hidden");
    };

    img.onerror = () => {
      resetTimers();
      spinner.style.display = "none";
      statusText.textContent = "Image generation failed.";
      fallbackText.textContent = "The image could not be generated.";
      fallbackText.classList.add("error");
      actions.classList.remove("hidden");
    };

    reloadBtn.addEventListener("click", startLoading);

    startLoading();
  </script>
</body>
</html>
"""

@app.get("/")
def index():
    return render_template_string(INDEX_HTML)

@app.get("/healthz")
def healthz():
    return jsonify({"ok": True})

@app.get("/silver-members.png")
def silver_members_png():
    png_bytes = generate_collage_png()
    return Response(
        png_bytes,
        mimetype="image/png",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
