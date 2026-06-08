# Google Drive File Transfer

A Python script to transfer folders between two Google Drive accounts mounted locally via Google Drive for Desktop, using rsync with dry-run support and post-transfer verification.

## Why

When moving large folders between Google Drive accounts (e.g. from a personal account to an archive account), downloading and re-uploading wastes bandwidth and time. If both accounts are mounted locally via Google Drive for Desktop, rsync can transfer files directly between them at full local speed.

## Features

- Transfers folders between any two locally mounted Google Drive paths
- **Dry-run mode** (`--dry-run`): simulates the transfer without copying anything
- **Post-transfer verification**: compares file counts folder by folder to confirm completeness
- Handles Unicode normalization differences between Google Drive accounts (NFC vs NFD) — avoids false negatives in verification
- Warns about broken symlinks and Google Drive shortcuts without failing
- Detects extra files in destination (e.g. `.docx` conversions from ZIP exports) without flagging them as errors

## Requirements

- Python 3.6+
- `rsync` (pre-installed on macOS and Linux)
- Both Google Drive accounts mounted via [Google Drive for Desktop](https://www.google.com/drive/download/)

## Usage

```bash
# Simulate first (no files copied)
python gdrive_transfer.py "/path/to/source" "/path/to/destination" --dry-run

# Run the actual transfer
python gdrive_transfer.py "/path/to/source" "/path/to/destination"
```

## Example

```bash
python gdrive_transfer.py \
  "/Users/you/Library/CloudStorage/GoogleDrive-work@company.com/My Drive/_ARCHIVE/ProjectX" \
  "/Users/you/Library/CloudStorage/GoogleDrive-archive@company.com/My Drive/_WORKS/ProjectX"
```

```
Sorgente : .../GoogleDrive-work@company.com/My Drive/_ARCHIVE/ProjectX
Destinazione: .../GoogleDrive-archive@company.com/My Drive/_WORKS/ProjectX
File da trasferire: 5755

Procedere con il trasferimento? [y/N] y

...

Verifica OK — tutte le sottocartelle hanno il numero atteso di file.
  Sorgente    : 5755 file
  Destinazione: 6282 file
  Extra       : 527 file (conversioni da ZIP o file preesistenti)
```
