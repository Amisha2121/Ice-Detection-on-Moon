"""
process_downloads.py
Scans the Downloads folder for any Chandrayaan-2 files (ch2_sar*, ch2_ohr*),
copies them to their raw directories, and extracts them if they are zip files.
"""

import os
import glob
import shutil
import zipfile

DOWNLOADS_DIR = r"C:\Users\AMISHA\Downloads"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DFSAR = os.path.join(ROOT, "data", "raw", "dfsar")
RAW_OHRC  = os.path.join(ROOT, "data", "raw", "ohrc")

os.makedirs(RAW_DFSAR, exist_ok=True)
os.makedirs(RAW_OHRC, exist_ok=True)

def process_zips(pattern, target_dir, name_prefix):
    files = glob.glob(os.path.join(DOWNLOADS_DIR, pattern))
    if not files:
        print(f"No files matching {pattern} found in Downloads.")
        return False
    
    for f in files:
        base = os.path.basename(f)
        # Skip active download temp files
        if base.endswith(".crdownload") or base.endswith(".tmp"):
            print(f"Skipping active download: {base}")
            continue
            
        dst_zip = os.path.join(target_dir, base)
        print(f"Found {name_prefix} file: {base}")
        
        # Check if already extracted
        # (We assume it's extracted if the directory has contents other than the zip itself)
        # Let's copy it if it's not present in target_dir
        if not os.path.exists(dst_zip):
            print(f"  Copying {base} to {target_dir}...")
            shutil.copy2(f, dst_zip)
        else:
            print(f"  {base} already copied.")
            
        if zipfile.is_zipfile(dst_zip):
            # Check if already extracted (e.g. folder with same name minus .zip exists)
            extract_folder = os.path.join(target_dir, base.replace(".zip", ""))
            if not os.path.exists(extract_folder) or len(os.listdir(extract_folder)) == 0:
                print(f"  Extracting {base}...")
                with zipfile.ZipFile(dst_zip, 'r') as ref:
                    ref.extractall(extract_folder)
                print(f"  Extracted to {extract_folder}")
            else:
                print(f"  Already extracted to {extract_folder}")
    return True

print("Processing downloads...")
sar_found = process_zips("ch2_sar*", RAW_DFSAR, "DFSAR")
ohr_found = process_zips("ch2_ohr*", RAW_OHRC, "OHRC")
print("Process finished.")
