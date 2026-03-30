from flask import Flask, Response, jsonify
from collage import generate_collage_png

app = Flask(__name__)

@app.get("/")
def health():
    return jsonify({
        "ok": True,
        "endpoint": "/silver-members.png"
    })

@app.get("/silver-members.png")
def silver_members_png():
    png_bytes = generate_collage_png()
    return Response(png_bytes, mimetype="image/png")
