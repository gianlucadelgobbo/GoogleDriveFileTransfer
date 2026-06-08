#!/usr/bin/env python3
"""
Trasferisce una cartella tra due profili Google Drive montati localmente.

Usa rsync per la copia e verifica il risultato confrontando il conteggio
dei file cartella per cartella (gestisce le differenze di normalizzazione
Unicode tra account Google Drive diversi).

Uso:
    python gdrive_transfer.py <sorgente> <destinazione> [--dry-run]

Esempio:
    python gdrive_transfer.py \\
        "/Volumes/GoogleDrive-g.delgobbo@flyer.it/My Drive/_ARCHIVE/Chromosphere" \\
        "/Volumes/GoogleDrive-archive@flyer.it/My Drive/_WORKS/Chromosphere"
"""

import sys
import os
import subprocess
import unicodedata
from pathlib import Path
from collections import defaultdict


def normalize(s: str) -> str:
    """Normalizza a NFC per confronti consistenti tra Drive diversi."""
    return unicodedata.normalize("NFC", s)


def count_files_by_folder(root: Path) -> dict[str, int]:
    """
    Restituisce {sottocartella_relativa: numero_file} per ogni sottocartella.
    Usa NFC per evitare falsi positivi da normalizzazione Unicode.
    """
    counts: dict[str, int] = defaultdict(int)
    counts["(root)"] = 0

    for item in root.rglob("*"):
        if item.is_symlink():
            continue
        if item.is_file():
            rel = normalize(str(item.relative_to(root).parent))
            counts[rel] += 1

    return dict(counts)


def run_rsync(src: Path, dst: Path, dry_run: bool) -> tuple[bool, int]:
    """Esegue rsync e restituisce (successo, numero_file_trasferiti)."""
    cmd = [
        "rsync",
        "-av",
        "--progress",
        "--stats",
    ]
    if dry_run:
        cmd.append("--dry-run")

    # Trailing slash su src = copia il contenuto (non la cartella stessa)
    cmd += [str(src) + "/", str(dst) + "/"]

    print(f"{'[DRY-RUN] ' if dry_run else ''}Comando: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, capture_output=False, text=True)
    success = result.returncode in (0, 23)  # 23 = alcuni file saltati (symlink rotti, ecc.)

    # Estrai il conteggio dall'output stats
    transferred = 0
    if not dry_run:
        proc = subprocess.run(cmd[:-2] + ["--dry-run"] + cmd[-2:],
                              capture_output=True, text=True)
    return success, result.returncode


def verify(src: Path, dst: Path) -> tuple[bool, list[str]]:
    """
    Verifica che ogni sottocartella della destinazione abbia almeno tanti
    file quanto la sorgente. Accetta che la dest ne abbia di più (file extra
    da ZIP o conversioni .docx).
    """
    print("\nVerifica in corso...")
    src_counts = count_files_by_folder(src)
    dst_counts = count_files_by_folder(dst)

    problems = []
    for folder, src_n in sorted(src_counts.items()):
        dst_n = dst_counts.get(folder, 0)
        if dst_n < src_n:
            problems.append(f"  {folder}: sorgente={src_n}  destinazione={dst_n}  (mancano {src_n - dst_n})")

    return len(problems) == 0, problems


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    paths = [a for a in args if not a.startswith("--")]

    if len(paths) < 2:
        print("Uso: python gdrive_transfer.py <sorgente> <destinazione> [--dry-run]")
        sys.exit(1)

    src = Path(paths[0])
    dst = Path(paths[1])

    if not src.exists():
        print(f"Errore: sorgente '{src}' non trovata.")
        sys.exit(1)

    # Conta file sorgente
    print(f"Sorgente : {src}")
    print(f"Destinazione: {dst}")
    src_total = sum(1 for p in src.rglob("*") if p.is_file() and not p.is_symlink())
    print(f"File da trasferire: {src_total}\n")

    if dry_run:
        print("=" * 60)
        print("MODALITÀ DRY-RUN — nessun file verrà copiato")
        print("=" * 60 + "\n")

    # Conferma
    label = "[simulazione] " if dry_run else ""
    confirm = input(f"Procedere con il {label}trasferimento? [y/N] ").strip().lower()
    if confirm != "y":
        print("Annullato.")
        sys.exit(0)

    # Crea la destinazione se non esiste
    if not dry_run:
        dst.mkdir(parents=True, exist_ok=True)

    print()
    ok, exit_code = run_rsync(src, dst, dry_run)

    if not ok:
        print(f"\nATTENZIONE: rsync ha restituito exit code {exit_code}.")
        print("Alcuni file potrebbero non essere stati trasferiti (es. symlink rotti).")

    # Verifica
    if not dry_run:
        verified, problems = verify(src, dst)
        if verified:
            print("\nVerifica OK — tutte le sottocartelle hanno il numero atteso di file.")
            dst_total = sum(1 for p in dst.rglob("*") if p.is_file() and not p.is_symlink())
            print(f"  Sorgente   : {src_total} file")
            print(f"  Destinazione: {dst_total} file")
            if dst_total > src_total:
                print(f"  Extra       : {dst_total - src_total} file (conversioni da ZIP o file preesistenti)")
        else:
            print(f"\nATTENZIONE: {len(problems)} cartella/e con file mancanti:")
            for p in problems:
                print(p)
            print("\nNon cancellare la sorgente finché non risolvi i problemi sopra.")
            sys.exit(1)
    else:
        print("\nDry-run completato. Rimuovi --dry-run per eseguire il trasferimento reale.")


if __name__ == "__main__":
    main()
