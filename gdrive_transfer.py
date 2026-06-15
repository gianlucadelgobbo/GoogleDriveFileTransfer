#!/usr/bin/env python3
"""
Trasferisce una cartella tra due account Google Drive usando rclone.
Copia server-side — i file viaggiano tra i server Google senza passare dal Mac.

Accetta percorsi locali CloudStorage o percorsi rclone:

  Locale (auto-rileva account):
    /Users/.../CloudStorage/GoogleDrive-account@domain.it/My Drive/cartella

  rclone remote:
    account@domain.it:cartella
    NomeRemote:cartella

Uso:
    python gdrive_transfer.py <sorgente> <destinazione> [--dry-run]

Esempio con percorsi locali:
    python3 gdrive_transfer.py \\
        "/Users/me/Library/CloudStorage/GoogleDrive-a@x.it/My Drive/_ARCHIVE/Foto" \\
        "/Users/me/Library/CloudStorage/GoogleDrive-b@x.it/My Drive/_WORKS/Foto"

Esempio con email:
    python gdrive_transfer.py "a@x.it:_ARCHIVE/Foto" "b@x.it:_WORKS/Foto"
"""

import re
import sys
import json
import subprocess


# --------------------------------------------------------------------------- #
# Remote rclone                                                                #
# --------------------------------------------------------------------------- #

def email_to_remote_name(email: str) -> str:
    return "gdrive_" + re.sub(r"[^a-zA-Z0-9]", "_", email)


def remote_exists(name: str) -> bool:
    result = subprocess.run(["rclone", "listremotes"], capture_output=True, text=True)
    return f"{name}:" in result.stdout


def ensure_remote(email: str, remote_name: str):
    """Crea il remote rclone per l'account se non esiste, con OAuth browser."""
    if remote_exists(remote_name):
        return

    print(f"\nNessun remote trovato per {email}.")
    print(f"Verrà creato il remote '{remote_name}'.")
    print("Il browser si aprirà: accedi con l'account Google corretto.\n")
    input("Premi INVIO per aprire il browser di autorizzazione...")

    subprocess.run(
        ["rclone", "config", "create", remote_name, "drive", "scope", "drive"],
        check=True,
    )
    subprocess.run(["rclone", "config", "reconnect", f"{remote_name}:"], check=True)
    print(f"\nRemote '{remote_name}' configurato.\n")


# --------------------------------------------------------------------------- #
# Parsing percorsi                                                             #
# --------------------------------------------------------------------------- #

def parse_path(path_str: str) -> str:
    """
    Converte qualsiasi formato di percorso in remote:path per rclone.

    Formati accettati:
      - /Users/.../CloudStorage/GoogleDrive-email/My Drive/path  → auto-config
      - email@domain.it:path                                      → auto-config
      - RemoteGiaConfigurato:path                                 → usato direttamente
    """
    # Percorso locale CloudStorage
    if path_str.startswith("/"):
        match = re.search(r"GoogleDrive-([^/]+)/My Drive/(.*)", path_str)
        if not match:
            print(f"Errore: percorso non riconosciuto:\n  {path_str}")
            print("Deve contenere 'GoogleDrive-account@domain/My Drive/...'")
            sys.exit(1)
        email = match.group(1)
        drive_path = match.group(2).rstrip("/")
        remote_name = email_to_remote_name(email)
        ensure_remote(email, remote_name)
        return f"{remote_name}:{drive_path}"

    # Formato con ":" → remote:path oppure email:path
    if ":" in path_str:
        prefix, drive_path = path_str.split(":", 1)
        drive_path = drive_path.lstrip("/").rstrip("/")
        if "@" in prefix:
            # È un'email
            remote_name = email_to_remote_name(prefix)
            ensure_remote(prefix, remote_name)
            return f"{remote_name}:{drive_path}"
        # È già un nome remote rclone
        return f"{prefix}:{drive_path}"

    print(f"Errore: formato percorso non valido: {path_str}")
    sys.exit(1)


# --------------------------------------------------------------------------- #
# Trasferimento e verifica                                                     #
# --------------------------------------------------------------------------- #

def rclone_size(remote: str) -> tuple[int, int]:
    result = subprocess.run(
        ["rclone", "size", remote, "--json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return 0, 0
    data = json.loads(result.stdout)
    return data.get("count", 0), data.get("bytes", 0)


def rclone_copy(src: str, dst: str, dry_run: bool, client_only: bool = False) -> bool:
    flags = ["--progress", "-v"]
    if dry_run:
        flags.append("--dry-run")

    if not client_only:
        # Primo tentativo: server-side (zero traffico locale se funziona)
        cmd1 = ["rclone", "copy", src, dst, "--drive-server-side-across-configs"] + flags
        print(f"{'[DRY-RUN] ' if dry_run else ''}Passaggio 1 (server-side): {' '.join(cmd1)}\n")
        subprocess.run(cmd1)

        if dry_run:
            return True

        print()

    # Passaggio streaming: copia i file mancanti (o tutti se --client-only)
    # rclone salta automaticamente i file già presenti nella destinazione
    cmd2 = ["rclone", "copy", src, dst] + flags
    label = "Passaggio streaming" if not client_only else "Trasferimento (client-only)"
    print(f"{label}: {' '.join(cmd2)}\n")
    result = subprocess.run(cmd2)
    return result.returncode == 0


def verify(src: str, dst: str) -> bool:
    print("\nVerifica in corso...")
    result = subprocess.run(
        ["rclone", "check", src, dst, "--one-way"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stderr)
    return result.returncode == 0


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #

def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    client_only = "--client-only" in args
    paths = [a for a in args if not a.startswith("--")]

    if len(paths) < 2:
        print("Uso: python gdrive_transfer.py <sorgente> <destinazione> [--dry-run]")
        sys.exit(1)

    src = parse_path(paths[0])
    dst = parse_path(paths[1])

    print(f"Sorgente    : {src}")
    print(f"Destinazione: {dst}")

    src_count, src_bytes = rclone_size(src)
    print(f"File da trasferire: {src_count} ({src_bytes / 1_000_000:.1f} MB)\n")

    if dry_run:
        print("=" * 60)
        print("MODALITÀ DRY-RUN — nessun file verrà copiato")
        print("=" * 60 + "\n")

    label = "[simulazione] " if dry_run else ""
    confirm = input(f"Procedere con il {label}trasferimento? [y/N] ").strip().lower()
    if confirm != "y":
        print("Annullato.")
        sys.exit(0)

    print()
    ok = rclone_copy(src, dst, dry_run, client_only)

    if not ok:
        print("\nATTENZIONE: rclone ha riportato errori durante il trasferimento.")
        sys.exit(1)

    if not dry_run:
        if verify(src, dst):
            dst_count, dst_bytes = rclone_size(dst)
            print("\nVerifica OK — tutti i file sono presenti nella destinazione.")
            print(f"  Sorgente    : {src_count} file ({src_bytes / 1_000_000:.1f} MB)")
            print(f"  Destinazione: {dst_count} file ({dst_bytes / 1_000_000:.1f} MB)")
            if dst_count > src_count:
                print(f"  Extra       : {dst_count - src_count} file preesistenti nella destinazione")
        else:
            print("\nATTENZIONE: la verifica ha rilevato file mancanti nella destinazione.")
            print("Non eliminare la sorgente finché non risolvi il problema.")
            sys.exit(1)
    else:
        print("\nDry-run completato. Rimuovi --dry-run per eseguire il trasferimento reale.")


if __name__ == "__main__":
    main()
