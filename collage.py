import os
import io
import math
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageChops
import cairosvg
from urllib.parse import urljoin, urlparse, unquote

OUTPUT_WIDTH = 3000
OUTPUT_HEIGHT = 1360
MEMBERS_URL = "https://www.zephyrproject.org/project-members/"
CACHE_DIR = "/tmp/logo_cache"

MAX_LOGO_WIDTH = 300
MAX_LOGO_HEIGHT = 80
CELL_ASPECT_RATIO = 3.0
PADDING = 40
MARGIN = 0

LOGO_SCALE_OVERRIDES = {
    "inovex": 1.2,
    "baylibre": 1.2,
}

def fetch_page_content(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; silver-members-collage/1.0)"
    }
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.text

def extract_silver_member_logos(html_content):
    soup = BeautifulSoup(html_content, "html.parser")

    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    silver_header = None
    associate_header = None

    for h in headings:
        text = h.get_text(strip=True)
        if "Silver Members" in text:
            silver_header = h
        elif "Associate Members" in text:
            associate_header = h

    if not silver_header:
        raise ValueError("Could not find Silver Members section")

    silver_logos = []
    in_silver_section = False

    for element in soup.descendants:
        if element == silver_header:
            in_silver_section = True
            continue
        if element == associate_header:
            in_silver_section = False
            break

        if in_silver_section and getattr(element, "name", None) == "img":
            src = element.get("src", "")
            if src and "zephyr_logo" not in src.lower():
                parent_a = element.find_parent("a")
                silver_logos.append({
                    "src": src,
                    "alt": element.get("alt", ""),
                    "href": parent_a.get("href", "") if parent_a else "",
                })

    return silver_logos

def get_safe_filename(url):
    parsed = urlparse(url)
    path = unquote(parsed.path)
    filename = os.path.basename(path) or "unknown_logo"
    name, ext = os.path.splitext(filename)
    clean_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip()
    if not clean_name:
        clean_name = "image"
    return f"{clean_name}{ext}"

def download_image(url, cache_dir):
    os.makedirs(cache_dir, exist_ok=True)

    filename = get_safe_filename(url)
    cache_path = os.path.join(cache_dir, filename)

    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return f.read(), filename

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; silver-members-collage/1.0)"
    }
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()

    with open(cache_path, "wb") as f:
        f.write(response.content)

    return response.content, filename

def convert_to_pil_image(image_data, filename):
    if filename.lower().endswith(".svg"):
        png_data = cairosvg.svg2png(
            bytestring=image_data,
            output_width=2048,
            output_height=2048,
        )
        img = Image.open(io.BytesIO(png_data))
    else:
        img = Image.open(io.BytesIO(image_data))

    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img

def get_logo_visual_bounds(img):
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    alpha = img.split()[3]
    alpha_bbox = alpha.getbbox()
    if not alpha_bbox:
        return None

    white_bg = Image.new("RGB", img.size, (255, 255, 255))
    composite = Image.new("RGB", img.size, (255, 255, 255))
    composite.paste(img, mask=alpha)

    diff = ImageChops.difference(composite, white_bg)
    gray_diff = diff.convert("L")
    thresholded = gray_diff.point(lambda x: 255 if x > 10 else 0)

    content_bbox = thresholded.getbbox()
    return content_bbox or alpha_bbox

def get_scale_override(logo_name, overrides):
    logo_name_lower = logo_name.lower()
    for key, scale in overrides.items():
        if key.lower() in logo_name_lower:
            return scale
    return 1.0

def normalize_logo_size(img, max_width, max_height):
    bbox = get_logo_visual_bounds(img)
    if not bbox:
        return img

    cropped = img.crop(bbox)
    if cropped.width == 0 or cropped.height == 0:
        return cropped

    width_ratio = max_width / cropped.width
    height_ratio = max_height / cropped.height
    scale = min(width_ratio, height_ratio)

    if scale != 1.0:
        new_width = max(1, int(cropped.width * scale))
        new_height = max(1, int(cropped.height * scale))
        return cropped.resize((new_width, new_height), Image.Resampling.LANCZOS)

    return cropped

def apply_scale_override(img, scale_ratio):
    if scale_ratio == 1.0:
        return img
    new_width = max(1, int(img.width * scale_ratio))
    new_height = max(1, int(img.height * scale_ratio))
    return img.resize((new_width, new_height), Image.Resampling.LANCZOS)

def calculate_grid_layout(num_logos, canvas_width, canvas_height, margin, padding, cell_aspect_ratio):
    available_width = canvas_width - 2 * margin
    available_height = canvas_height - 2 * margin

    best_layout = None
    best_area = 0

    for num_rows in range(1, num_logos + 1):
        num_cols = math.ceil(num_logos / num_rows)

        max_cell_height_from_width = available_width / (num_cols * cell_aspect_ratio)
        max_cell_height_from_height = available_height / num_rows

        cell_height = min(max_cell_height_from_width, max_cell_height_from_height)
        cell_width = cell_height * cell_aspect_ratio
        cell_area = cell_width * cell_height

        if num_cols * num_rows >= num_logos and cell_area > best_area:
            best_area = cell_area
            best_layout = (num_rows, num_cols, cell_width, cell_height)

    if best_layout:
        return best_layout

    num_cols = math.ceil(math.sqrt(num_logos * available_width / available_height))
    num_rows = math.ceil(num_logos / num_cols)
    cell_height = available_height / num_rows
    cell_width = cell_height * cell_aspect_ratio
    return (num_rows, num_cols, cell_width, cell_height)

def create_collage(logos, output_width, output_height, margin, padding, cell_aspect_ratio):
    num_logos = len(logos)
    num_rows, num_cols, cell_width, cell_height = calculate_grid_layout(
        num_logos, output_width, output_height, margin, padding, cell_aspect_ratio
    )

    canvas = Image.new("RGBA", (output_width, output_height), (255, 255, 255, 255))
    total_grid_width = num_cols * cell_width
    total_grid_height = num_rows * cell_height

    start_x = (output_width - total_grid_width) / 2
    start_y = (output_height - total_grid_height) / 2

    for idx, logo in enumerate(logos):
        row = idx // num_cols
        col = idx % num_cols

        cell_x = start_x + col * cell_width
        cell_y = start_y + row * cell_height

        logo_max_width = cell_width - 2 * padding
        logo_max_height = cell_height - 2 * padding

        scale = min(logo_max_width / logo.width, logo_max_height / logo.height)
        if scale < 1.0:
            new_width = int(logo.width * scale)
            new_height = int(logo.height * scale)
            logo = logo.resize((new_width, new_height), Image.Resampling.LANCZOS)

        logo_x = int(cell_x + (cell_width - logo.width) / 2)
        logo_y = int(cell_y + (cell_height - logo.height) / 2)

        canvas.paste(logo, (logo_x, logo_y), logo)

    return canvas

def _progress(progress_callback, step, message, fraction, **extra):
    if not progress_callback:
        return
    payload = {"step": step, "message": message, "fraction": fraction, **extra}
    progress_callback(payload)


def generate_collage_png(progress_callback=None):
    """
    progress_callback receives a dict with at least:
      step, message, fraction (0.0–1.0), and optional current/total/label.
    """
    _progress(progress_callback, "fetch_page", "Fetching member page…", 0.0)
    html_content = fetch_page_content(MEMBERS_URL)

    _progress(progress_callback, "parse_logos", "Parsing Silver Members section…", 0.06)
    logo_infos = extract_silver_member_logos(html_content)

    if not logo_infos:
        raise RuntimeError("No silver member logos found")

    n = len(logo_infos)
    # Reserve ~0.06–0.82 for per-logo work (download + normalize).
    span = 0.76

    processed_logos = []
    for i, info in enumerate(logo_infos, start=1):
        label = (info.get("alt") or "").strip() or f"logo {i}"
        frac = 0.06 + span * (i - 1) / max(n, 1)
        _progress(
            progress_callback,
            "logo",
            f"Logo {i}/{n}: {label}",
            frac,
            current=i,
            total=n,
            label=label,
        )

        url = info["src"]
        if not url.startswith("http"):
            url = urljoin(MEMBERS_URL, url)

        image_data, filename = download_image(url, CACHE_DIR)
        img = convert_to_pil_image(image_data, filename)

        if img.width > 0 and img.height > 0:
            normalized = normalize_logo_size(img, MAX_LOGO_WIDTH, MAX_LOGO_HEIGHT)
            logo_name = info.get("alt", "") or filename
            scale_override = get_scale_override(logo_name, LOGO_SCALE_OVERRIDES)
            normalized = apply_scale_override(normalized, scale_override)
            processed_logos.append(normalized)

    if not processed_logos:
        raise RuntimeError("No logos processed successfully")

    _progress(progress_callback, "render_collage", "Building grid and rendering collage…", 0.86)
    collage = create_collage(
        processed_logos,
        OUTPUT_WIDTH,
        OUTPUT_HEIGHT,
        MARGIN,
        PADDING,
        CELL_ASPECT_RATIO,
    )

    _progress(progress_callback, "encode_png", "Encoding PNG…", 0.94)
    output = io.BytesIO()
    rgb = Image.new("RGB", collage.size, (255, 255, 255))
    rgb.paste(collage, mask=collage.split()[3] if collage.mode == "RGBA" else None)
    rgb.save(output, format="PNG")
    output.seek(0)
    _progress(progress_callback, "done", "Done.", 1.0)
    return output.getvalue()
