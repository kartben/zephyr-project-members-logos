import json
import queue
import secrets
import threading

from flask import Flask, Response, render_template_string, request, url_for, jsonify, stream_with_context
from collage import generate_collage_png

app = Flask(__name__)

# One-time PNG handoff after SSE generation completes (token -> bytes).
_png_tokens = {}
_png_tokens_lock = threading.Lock()

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

    .progress-track {
      width: 100%;
      max-width: 560px;
      height: 8px;
      border-radius: 999px;
      background: rgba(127, 127, 127, 0.25);
      overflow: hidden;
      margin-bottom: 0.75rem;
    }

    .progress-fill {
      height: 100%;
      width: 0%;
      border-radius: inherit;
      background: color-mix(in srgb, CanvasText 70%, transparent);
      transition: width 0.2s ease-out;
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

    <div class="progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" id="progress-track">
      <div class="progress-fill" id="progress-fill"></div>
    </div>

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
    const progressFill = document.getElementById("progress-fill");
    const progressTrack = document.getElementById("progress-track");

    let eventSource = null;
    let stallTimer = null;
    let streamFinished = false;

    function resetLoadingState() {
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
      if (stallTimer) {
        clearTimeout(stallTimer);
        stallTimer = null;
      }
    }

    function setProgressFraction(fraction) {
      const pct = Math.round(Math.max(0, Math.min(1, fraction)) * 100);
      progressFill.style.width = pct + "%";
      progressTrack.setAttribute("aria-valuenow", String(pct));
    }

    function startLoading() {
      resetLoadingState();
      streamFinished = false;

      img.style.display = "none";
      img.removeAttribute("src");
      fallbackText.textContent = "Waiting for the image…";
      fallbackText.classList.remove("error");
      actions.classList.add("hidden");
      spinner.style.display = "block";
      statusText.textContent = "Starting image generation…";
      setProgressFraction(0);

      const streamUrl = "{{ url_for('collage_progress_stream') }}?t=" + Date.now();
      eventSource = new EventSource(streamUrl);

      function armStallWarning() {
        if (stallTimer) clearTimeout(stallTimer);
        stallTimer = setTimeout(() => {
          statusText.textContent = "Still working… (no update for a while; large downloads can pause here.)";
        }, 45000);
      }

      armStallWarning();

      eventSource.onmessage = (ev) => {
        armStallWarning();
        let data;
        try {
          data = JSON.parse(ev.data);
        } catch (e) {
          return;
        }

        if (data.type === "error") {
          streamFinished = true;
          resetLoadingState();
          spinner.style.display = "none";
          statusText.textContent = "Image generation failed.";
          fallbackText.textContent = data.message || "The image could not be generated.";
          fallbackText.classList.add("error");
          actions.classList.remove("hidden");
          setProgressFraction(0);
          return;
        }

        if (data.type === "complete") {
          streamFinished = true;
          resetLoadingState();
          const token = data.token;
          const imageUrl =
            "{{ url_for('silver_members_png') }}?token=" +
            encodeURIComponent(token) +
            "&t=" +
            Date.now();
          img.src = imageUrl;
          return;
        }

        if (typeof data.fraction === "number") {
          setProgressFraction(data.fraction);
        }
        if (data.message) {
          statusText.textContent = data.message;
        }
      };

      eventSource.onerror = () => {
        if (streamFinished) {
          return;
        }
        resetLoadingState();
        spinner.style.display = "none";
        statusText.textContent = "Connection lost.";
        fallbackText.textContent = "Could not read generation progress. Try again.";
        fallbackText.classList.add("error");
        actions.classList.remove("hidden");
        setProgressFraction(0);
      };
    }

    img.onload = () => {
      resetLoadingState();
      spinner.style.display = "none";
      statusText.textContent = "Done.";
      fallbackText.textContent = "";
      img.style.display = "block";
      actions.classList.remove("hidden");
      setProgressFraction(1);
    };

    img.onerror = () => {
      resetLoadingState();
      spinner.style.display = "none";
      statusText.textContent = "Image generation failed.";
      fallbackText.textContent = "The image could not be generated.";
      fallbackText.classList.add("error");
      actions.classList.remove("hidden");
      setProgressFraction(0);
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


@app.get("/api/collage/stream")
def collage_progress_stream():
    """Server-Sent Events: real progress from `generate_collage_png`, then a one-time image token."""

    @stream_with_context
    def event_stream():
        q = queue.Queue()
        result_holder = {}
        error_holder = {}

        def worker():
            try:

                def progress(payload):
                    q.put(("progress", payload))

                png = generate_collage_png(progress_callback=progress)
                result_holder["png"] = png
            except Exception as e:
                error_holder["error"] = str(e)
            finally:
                q.put(("done", None))

        threading.Thread(target=worker, daemon=True).start()

        while True:
            kind, data = q.get()
            if kind == "done":
                break
            yield f"data: {json.dumps(data)}\n\n"

        if error_holder.get("error"):
            yield f"data: {json.dumps({'type': 'error', 'message': error_holder['error']})}\n\n"
        elif "png" in result_holder:
            token = secrets.token_urlsafe(24)
            with _png_tokens_lock:
                _png_tokens[token] = result_holder["png"]
            yield f"data: {json.dumps({'type': 'complete', 'token': token})}\n\n"

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/silver-members.png")
def silver_members_png():
    token = request.args.get("token")
    if token:
        with _png_tokens_lock:
            png_bytes = _png_tokens.pop(token, None)
        if png_bytes is None:
            return Response(
                "Image not found or token already used.",
                status=404,
                mimetype="text/plain",
            )
    else:
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
