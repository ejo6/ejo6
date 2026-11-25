#!/usr/bin/env python3
"""Generate a Spotify-style "Song of the Week" SVG card from a track link.

Usage:
    python3 scripts/song_card.py 'https://open.spotify.com/track/TRACK_ID'
    python3 scripts/song_card.py LINK -o assets/custom.svg
    python3 scripts/song_card.py LINK --dir assets --progress 0.6

By default the card is written to assets/song-of-the-week-<i>.svg, where <i> is
one more than the highest existing index in that folder (starting at 1).

Needs only the standard library. If Pillow is installed (pip install pillow) the
cover is also auto-cropped to remove white borders and shrunk to keep the SVG small.
"""

import argparse
import base64
import html
import io
import re
import sys
import urllib.request
from pathlib import Path

try:
    from PIL import Image, ImageChops
except ImportError:  # Pillow is optional
    Image = None

UA = "Mozilla/5.0 (song-card script)"
CARD_W, CARD_H = 440, 140
COVER_H = 108
PAD = 16


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


def parse_track_id(link: str) -> str:
    m = re.search(r"track/([A-Za-z0-9]{22})", link) or re.search(r"spotify:track:([A-Za-z0-9]{22})", link)
    if not m:
        sys.exit("Couldn't find a track ID in that link. Expected https://open.spotify.com/track/<id>")
    return m.group(1)


def meta(page: str, prop: str) -> str:
    m = re.search(r'<meta[^>]+(?:property|name)="%s"[^>]+content="([^"]*)"' % re.escape(prop), page)
    return html.unescape(m.group(1)) if m else ""


def get_track(track_id: str) -> dict:
    page = fetch(f"https://open.spotify.com/track/{track_id}").decode("utf-8", "replace")
    title = meta(page, "og:title")
    artist = meta(page, "music:musician_description") or meta(page, "og:description").split("·")[0].strip()
    image = meta(page, "og:image")
    if not (title and artist and image):
        sys.exit("Couldn't read the track's title/artist/cover from Spotify.")
    return {"title": title, "artist": artist, "image": image}


def prepare_cover(raw: bytes):
    """Return (jpeg_bytes, aspect_ratio w/h). Crops white borders if Pillow is available."""
    if Image is None:
        return raw, 1.0
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    # Crop near-white borders (some covers ship with a white margin).
    diff = ImageChops.difference(img, Image.new("RGB", img.size, (255, 255, 255)))
    diff = diff.point(lambda p: 255 if p > 15 else 0)
    box = diff.getbbox()
    if box:
        l, t, r, b = box
        has_border = (r - l) < img.width * 0.98 or (b - t) < img.height * 0.98
        if has_border:
            inset = round(img.width * 0.015)  # drop anti-aliased / ragged edge pixels
            l, t, r, b = l + inset, t + inset, r - inset, b - inset
            if r - l > img.width * 0.3 and b - t > img.height * 0.3:
                img = img.crop((l, t, r, b))
    img.thumbnail((400, 400))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue(), img.width / img.height


def fit_text(text: str, max_w: float, size: float, min_size: float):
    """Shrink font, then truncate, so text (approx. 0.56em/char bold) fits max_w."""
    def width(t, s):
        return len(t) * s * 0.56

    while width(text, size) > max_w and size > min_size:
        size -= 1
    while width(text, size) > max_w and len(text) > 1:
        text = text[:-1].rstrip()
        if width(text + "…", size) <= max_w:
            text += "…"
            break
    return text, size


def build_svg(track: dict, cover: bytes, aspect: float, progress: float) -> str:
    cover_w = round(max(80, min(COVER_H, COVER_H * aspect)))
    text_x = PAD + cover_w + 20
    text_w = CARD_W - text_x - PAD
    title, title_size = fit_text(track["title"], text_w, 22, 15)
    artist, artist_size = fit_text(track["artist"], text_w, 14, 11)
    bar_w = text_w
    fill_w = round(bar_w * progress)
    b64 = base64.b64encode(cover).decode()
    esc = lambda s: html.escape(s, quote=True)
    label = esc(f"Song of the Week: {track['title']} by {track['artist']}")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{CARD_W}" height="{CARD_H}" viewBox="0 0 {CARD_W} {CARD_H}" role="img" aria-label="{label}">
  <defs>
    <clipPath id="cover"><rect x="{PAD}" y="{PAD}" width="{cover_w}" height="{COVER_H}" rx="6"/></clipPath>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#181818"/>
      <stop offset="1" stop-color="#050505"/>
    </linearGradient>
  </defs>
  <rect width="{CARD_W}" height="{CARD_H}" rx="14" fill="url(#bg)"/>
  <rect x="0.5" y="0.5" width="{CARD_W - 1}" height="{CARD_H - 1}" rx="13.5" fill="none" stroke="#2a2a2a"/>
  <image x="{PAD}" y="{PAD}" width="{cover_w}" height="{COVER_H}" clip-path="url(#cover)" preserveAspectRatio="xMidYMid slice" xlink:href="data:image/jpeg;base64,{b64}"/>
  <g font-family="-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif">
    <text x="{text_x}" y="42" fill="#1db954" font-size="11" font-weight="700" letter-spacing="1.5">SONG OF THE WEEK</text>
    <text x="{text_x}" y="72" fill="#ffffff" font-size="{title_size}" font-weight="700">{esc(title)}</text>
    <text x="{text_x}" y="94" fill="#b3b3b3" font-size="{artist_size}">{esc(artist)}</text>
  </g>
  <rect x="{text_x}" y="108" width="{bar_w}" height="4" rx="2" fill="#404040"/>
  <rect x="{text_x}" y="108" width="{fill_w}" height="4" rx="2" fill="#1db954"/>
  <circle cx="{text_x + fill_w}" cy="110" r="5" fill="#ffffff"/>
</svg>
"""


def next_path(folder: Path) -> Path:
    nums = [int(m.group(1)) for p in folder.glob("song-of-the-week-*.svg")
            if (m := re.fullmatch(r"song-of-the-week-(\d+)\.svg", p.name))]
    return folder / f"song-of-the-week-{max(nums, default=0) + 1}.svg"


def main():
    ap = argparse.ArgumentParser(description="Make a Spotify-style song card SVG from a track link.")
    ap.add_argument("link", help="Spotify track link (or spotify:track:ID)")
    ap.add_argument("-o", "--output", help="exact output path (overrides --dir auto-numbering)")
    ap.add_argument("--dir", default="assets", help="output folder for auto-numbered files (default: assets)")
    ap.add_argument("--progress", type=float, default=0.4, help="decorative progress bar, 0-1 (default 0.4)")
    args = ap.parse_args()

    track = get_track(parse_track_id(args.link))
    cover, aspect = prepare_cover(fetch(track["image"]))
    if Image is None:
        print("note: Pillow not installed, cover not cropped (pip install pillow)", file=sys.stderr)

    if args.output:
        out = Path(args.output)
    else:
        folder = Path(args.dir)
        folder.mkdir(parents=True, exist_ok=True)
        out = next_path(folder)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_svg(track, cover, aspect, max(0.0, min(1.0, args.progress))), encoding="utf-8")

    print(f"{track['title']} - {track['artist']}")
    print(f"wrote {out}")
    print(f"\n[![{track['title']} – {track['artist']}]({out.as_posix()})]({args.link.split('?')[0]})")


if __name__ == "__main__":
    main()
