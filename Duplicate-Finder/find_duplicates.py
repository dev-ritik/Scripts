import hashlib
import json
import os

from tqdm import tqdm


def compute_md5(file_path):
    """Compute the MD5 checksum of a file."""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except FileNotFoundError:
        return None  # Skip missing files


def main():
    file_list_path = "file_list.txt"
    progress_file = "progress.json"
    duplicates_file = "duplicates.json"
    base_path = "/media/ritik/Ritik/"

    # Load file list
    with open(file_list_path, "r") as f:
        files = [line.strip() for line in f.readlines()]

    # Randomize file order for parallel execution
    # random.shuffle(files)

    # Load progress if available
    if os.path.exists(progress_file):
        with open(progress_file, "r") as f:
            progress = json.load(f)
    else:
        progress = {"processed_files": [], "hashes": {}}

    # Initialize progress tracker
    hashes = progress["hashes"]
    processed_files = set(progress["processed_files"])

    # TODO: Implement multi processing

    # Process files with a progress bar
    with tqdm(total=len(files), desc="Processing files", unit="file") as pbar:
        pbar.update(len(processed_files))
        for file in files:
            if file in processed_files:
                continue  # Skip already processed files
            if file_md5 := compute_md5(f'{base_path}{file}'):
                hashes.setdefault(file_md5, []).append(file)
            else:
                print(f"{file=} md5 hash not found")
            processed_files.add(file)

            # Periodically save progress
            if len(processed_files) % 100 == 0:
                with open(progress_file, "w") as f:
                    json.dump({"processed_files": list(processed_files), "hashes": hashes}, f)

            pbar.update(1)

    # Save final results
    with open(progress_file, "w") as f:
        json.dump({"processed_files": list(processed_files), "hashes": hashes}, f)
    with open(duplicates_file, "w") as f:
        duplicates = {}
        for _hash, files in hashes.items():
            if len(files) > 1:
                duplicates[_hash] = files
        json.dump(duplicates, f, indent=4)

    print("Duplicate files saved to:", duplicates_file)


if __name__ == "__main__":
    main()
