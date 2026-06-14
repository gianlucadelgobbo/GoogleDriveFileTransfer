#!/usr/bin/env python3
"""
Ripristina i metadati EXIF nelle foto/video esportati da Google Takeout.

Google Takeout genera un file .json per ogni media con i metadati originali
(data scatto, GPS, descrizione) che non vengono scritti nel file stesso.
Questo script li applica usando exiftool.

Uso:
    python takeout_restore_metadata.py <cartella_takeout> [--dry-run]
"""

import sys
import json
import subprocess
import unicodedata
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional


MEDIA_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".bmp", ".tiff", ".tif",
    ".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".wmv", ".mts", ".m2ts",
}

JSON_SUFFIXES = [
    ".json",                           # photo.jpg.json
    ".supplemental-metadata.json",    # photo.jpg.supplemental-metadata.json (formato recente)
]


def normalize(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def find_json_for_media(media_path: Path) -> Optional[Path]:
    """
    Cerca il file JSON corrispondente al file media.
    Gestisce i vari pattern di naming di Google Takeout:
      - photo.jpg       → photo.jpg.json
      - photo.jpg       → photo.jpg.supplemental-metadata.json
      - photo(1).jpg    → photo.jpg(1).json   (duplicati)
      - photo.jpg       → photo.json          (nome troncato)
    """
    name = media_path.name   # es. "IMG_1234.jpg"
    stem = media_path.stem   # es. "IMG_1234"
    parent = media_path.parent

    candidates = [
        parent / (name + ".json"),
        parent / (name + ".supplemental-metadata.json"),
        parent / (stem + ".json"),
    ]

    # Gestione duplicati: "IMG_1234(1).jpg" → "IMG_1234.jpg(1).json"
    import re
    m = re.match(r"^(.+?)(\(\d+\))(\.\w+)$", name)
    if m:
        base, num, ext = m.group(1), m.group(2), m.group(3)
        candidates += [
            parent / (base + ext + num + ".json"),
            parent / (base + ext + num + ".supplemental-metadata.json"),
        ]

    for c in candidates:
        if c.exists():
            return c
    return None


def parse_json(json_path: Path) -> dict:
    """Legge il JSON di Takeout e restituisce i campi rilevanti."""
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {}

    result = {}

    # Data scatto
    for key in ("photoTakenTime", "creationTime"):
        if key in data and "timestamp" in data[key]:
            ts = int(data[key]["timestamp"])
            result["datetime"] = datetime.fromtimestamp(ts, tz=timezone.utc)
            break

    # GPS
    for key in ("geoDataExif", "geoData"):
        geo = data.get(key, {})
        lat = geo.get("latitude", 0.0)
        lon = geo.get("longitude", 0.0)
        if lat != 0.0 or lon != 0.0:
            result["latitude"] = lat
            result["longitude"] = lon
            result["altitude"] = geo.get("altitude", 0.0)
            break

    # Descrizione
    if data.get("description"):
        result["description"] = data["description"]

    return result


def build_exiftool_args(meta: dict, media_path: Path) -> list[str]:
    """Costruisce gli argomenti exiftool per scrivere i metadati."""
    args = ["-overwrite_original", "-m"]  # -m = ignora errori minori

    if "datetime" in meta:
        dt = meta["datetime"]
        dt_str = dt.strftime("%Y:%m:%d %H:%M:%S")
        tz_str = "+00:00"
        args += [
            f"-DateTimeOriginal={dt_str}",
            f"-CreateDate={dt_str}",
            f"-ModifyDate={dt_str}",
            f"-DateTimeOriginal+={tz_str}",
        ]

    if "latitude" in meta:
        lat, lon = meta["latitude"], meta["longitude"]
        alt = meta.get("altitude", 0.0)
        args += [
            f"-GPSLatitude={abs(lat)}",
            f"-GPSLatitudeRef={'N' if lat >= 0 else 'S'}",
            f"-GPSLongitude={abs(lon)}",
            f"-GPSLongitudeRef={'E' if lon >= 0 else 'W'}",
            f"-GPSAltitude={abs(alt)}",
            f"-GPSAltitudeRef={'0' if alt >= 0 else '1'}",
        ]

    if "description" in meta:
        desc = meta["description"].replace('"', '\\"')
        args.append(f"-Description={desc}")
        args.append(f"-ImageDescription={desc}")

    return args


def process_folder(root: Path, dry_run: bool):
    media_files = [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS
    ]

    print(f"File media trovati: {len(media_files)}")
    if dry_run:
        print("MODALITÀ DRY-RUN — nessuna modifica verrà apportata\n")

    ok = skipped = no_json = errors = 0

    for media in sorted(media_files):
        json_path = find_json_for_media(media)

        if json_path is None:
            no_json += 1
            continue

        meta = parse_json(json_path)
        if not meta:
            skipped += 1
            continue

        args = build_exiftool_args(meta, media)
        if not args or len(args) == 2:  # solo -overwrite_original -m, nessun dato utile
            skipped += 1
            continue

        rel = media.relative_to(root)
        dt_str = meta.get("datetime", "").strftime("%Y-%m-%d %H:%M") if "datetime" in meta else "—"
        gps = f"  GPS: {meta['latitude']:.4f},{meta['longitude']:.4f}" if "latitude" in meta else ""
        print(f"  {rel}  [{dt_str}]{gps}")

        if not dry_run:
            cmd = ["exiftool"] + args + [str(media)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"    ERRORE: {result.stderr.strip()}")
                errors += 1
            else:
                ok += 1
        else:
            ok += 1

    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Risultato:")
    print(f"  Aggiornati   : {ok}")
    print(f"  Senza JSON   : {no_json}")
    print(f"  Saltati      : {skipped} (JSON vuoto o nessun dato)")
    if errors:
        print(f"  Errori       : {errors}")


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    paths = [a for a in args if not a.startswith("--")]

    if not paths:
        print("Uso: python takeout_restore_metadata.py <cartella_takeout> [--dry-run]")
        sys.exit(1)

    root = Path(paths[0])
    if not root.exists():
        print(f"Errore: '{root}' non trovata.")
        sys.exit(1)

    # Verifica exiftool
    try:
        subprocess.run(["exiftool", "-ver"], capture_output=True, check=True)
    except FileNotFoundError:
        print("Errore: exiftool non trovato. Installalo con: brew install exiftool")
        sys.exit(1)

    process_folder(root, dry_run)


if __name__ == "__main__":
    main()
