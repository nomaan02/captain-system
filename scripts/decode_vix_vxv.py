"""
Decode VIX/VXV extraction output from QC research notebook.

Usage:
    python captain-system/scripts/decode_vix_vxv.py

Reads vix_vxv_raw.txt from project root, outputs to captain-system/data/vix/
"""
import re
import zlib
import base64
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INPUT_FILE = PROJECT_ROOT / "vix_vxv_raw.txt"
OUTPUT_DIR = PROJECT_ROOT / "captain-system" / "data" / "vix"

ZSTART_RE = re.compile(
    r"===ZSTART:(?P<tag>[^:]+):orig=(?P<orig>\d+):compressed=(?P<comp>\d+):chunks=(?P<chunks>\d+)==="
)
ZEND_RE = re.compile(r"===ZEND:(?P<tag>[^=]+)===")


def decode_file(raw_text: str) -> dict[str, str]:
    """Parse ZSTART/ZEND blocks and return {filename: decoded_content}."""
    results = {}
    lines = raw_text.split("\n")
    i = 0
    while i < len(lines):
        m = ZSTART_RE.search(lines[i])
        if m:
            tag = m.group("tag")
            orig_size = int(m.group("orig"))
            encoded_parts = []
            i += 1
            while i < len(lines):
                if ZEND_RE.search(lines[i]):
                    break
                stripped = lines[i].strip()
                if stripped:
                    encoded_parts.append(stripped)
                i += 1

            encoded = "".join(encoded_parts)
            try:
                compressed = base64.b64decode(encoded)
                raw_bytes = zlib.decompress(compressed)
                content = raw_bytes.decode("utf-8")
                results[tag] = content
                print(f"  Decoded {tag}: {len(content):,} bytes (expected {orig_size:,})")
                if len(content) != orig_size:
                    print(f"    WARNING: size mismatch — got {len(content)}, expected {orig_size}")
            except Exception as e:
                print(f"  FAILED {tag}: {e}")
        i += 1
    return results


def main():
    if not INPUT_FILE.exists():
        print(f"Input file not found: {INPUT_FILE}")
        print("Copy the QC notebook output into vix_vxv_raw.txt in the project root.")
        return

    print(f"Reading {INPUT_FILE}")
    raw = INPUT_FILE.read_text(encoding="utf-8")

    results = decode_file(raw)
    if not results:
        print("No ZSTART/ZEND blocks found in input!")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for filename, content in results.items():
        out_path = OUTPUT_DIR / filename
        out_path.write_text(content, encoding="utf-8")
        row_count = content.count("\n")
        print(f"  Saved {out_path} ({row_count} rows)")

    print(f"\nDone — {len(results)} files saved to {OUTPUT_DIR}")

    # Quick sanity check on IVTS if present
    ivts_path = OUTPUT_DIR / "ivts_daily.csv"
    if ivts_path.exists():
        lines = ivts_path.read_text().strip().split("\n")
        print(f"\nIVTS preview (last 5 rows):")
        for line in lines[-5:]:
            print(f"  {line}")


if __name__ == "__main__":
    main()
