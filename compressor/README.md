# File Compressor (Recursive)

A Python tool to recursively compress **images, audio, video, and PDF files** while keeping the same format.

---

## ✨ Features

* 🔁 **Recursive compression** of all subfolders
* 📁 Supports:

  * Images: JPG, JPEG, PNG, WEBP, HEIC, HEIF, WEBP
  * Audio: MP3, AAC, M4A, WAV, FLAC, OPUS
  * Video: MP4, MOV, MKV
  * PDF
* 📉 **Skips replacement if the compressed file is bigger**
* 🧪 **--dry-run flag** to keep originals untouched
* 📊 **Progress bar (tqdm)**
* 📝 **Logging** showing size saved per file
* 🛡 Safe temporary output usage before replacement
* `low`, `medium`, `high`, `extreme` compression levels
* Parallelization

---

## 🛠 Installation

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Install system dependencies

#### **FFmpeg**

Ubuntu:

```bash
sudo apt install ffmpeg
```

Mac:

```bash
brew install ffmpeg
```

#### **Ghostscript** (for PDF compression)

Ubuntu:

```bash
sudo apt install ghostscript
```

Mac:

```bash
brew install ghostscript
```

---

## 🚀 Usage

Run the script:

```bash
python compress.py /path/to/folder
```

### Dry run (do not replace files)

```bash
python compress.py /path/to/folder/**/* --mode extreme --dry-run
```

In dry-run mode, compressed files are written as:

```
file.compressed.<ext>
```