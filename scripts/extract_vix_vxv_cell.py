# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  VIX + VIX3M (VXV) Extraction Cell — QuantConnect Research Notebook        ║
# ║                                                                            ║
# ║  Paste this entire cell into QC research.ipynb and run.                    ║
# ║  Copy ALL console output, save to vix_vxv_raw.txt, then decode locally:   ║
# ║    python captain-system/scripts/decode_vix_vxv.py                         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

from QuantConnect import *
from QuantConnect.Research import *
from datetime import datetime
import csv, io, zlib, base64, time

# Try all known CBOE import paths (varies by QC version)
CBOE = None
for _path in [
    "QuantConnect.DataSource.CBOE",
    "QuantConnect.Data.Custom.CBOE.CBOE",
    "QuantConnect.Data.Custom.Cboe.CBOE",
]:
    try:
        _parts = _path.rsplit(".", 1)
        _mod = __import__(_parts[0], fromlist=[_parts[1]])
        CBOE = getattr(_mod, _parts[1])
        print(f"Found CBOE at: {_path}")
        break
    except (ImportError, AttributeError):
        continue

if CBOE is None:
    # Last resort: scan QuantConnect.DataSource namespace
    try:
        import QuantConnect.DataSource as ds
        for name in dir(ds):
            if name.upper() == "CBOE":
                CBOE = getattr(ds, name)
                print(f"Found CBOE via DataSource scan: {name}")
                break
    except ImportError:
        pass

if CBOE is None:
    print("ERROR: Could not find CBOE data type in any known location.")
    print("Listing available modules for debugging:")
    try:
        import QuantConnect.Data.Custom as cust
        print(f"  QuantConnect.Data.Custom contents: {dir(cust)}")
    except: pass
    try:
        import QuantConnect.DataSource as ds
        print(f"  QuantConnect.DataSource contents: {dir(ds)}")
    except: pass
    raise ImportError("CBOE data type not found — check QC docs for current import path")

qb = QuantBook()

# ── Config ────────────────────────────────────────────────────────────────────
START = datetime(2009, 1, 1)
END   = datetime(2026, 3, 23)
CHUNK_SIZE = 700_000  # bytes per console chunk

# ── Compression helper ────────────────────────────────────────────────────────
def print_compressed(tag, raw_str):
    raw_bytes = raw_str.encode("utf-8")
    compressed = zlib.compress(raw_bytes, 9)
    encoded = base64.b64encode(compressed).decode("ascii")
    n_chunks = (len(encoded) + CHUNK_SIZE - 1) // CHUNK_SIZE
    print(f"===ZSTART:{tag}:orig={len(raw_bytes)}:compressed={len(compressed)}:chunks={n_chunks}===")
    for i in range(n_chunks):
        if i > 0:
            time.sleep(3.5)
        chunk = encoded[i * CHUNK_SIZE : (i + 1) * CHUNK_SIZE]
        print(chunk, end="")
        if i < n_chunks - 1:
            print()
    print(f"\n===ZEND:{tag}===")

# ── Extract VIX ───────────────────────────────────────────────────────────────
print("=" * 60)
print("IVTS Data Extraction: VIX + VIX3M (VXV)")
print("=" * 60)

vix_csv = None
vxv_csv = None

# --- VIX (1-month implied vol) ---
try:
    vix_sym = qb.add_data(CBOE, "VIX", Resolution.DAILY)
    vix_hist = qb.history(vix_sym.symbol, START, END, Resolution.DAILY)

    if vix_hist is not None and len(vix_hist) > 0:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["date", "vix_close"])
        count = 0
        for idx, row in vix_hist.iterrows():
            dt = str(idx[1])[:10] if isinstance(idx, tuple) else str(idx)[:10]
            w.writerow([dt, f"{row['close']:.2f}"])
            count += 1
        vix_csv = buf.getvalue()
        print(f"VIX: {count:,} rows, range {str(vix_hist.index[0])[:10]} -> {str(vix_hist.index[-1])[:10]}")
    else:
        print("VIX: No data returned!")
except Exception as e:
    print(f"VIX ERROR: {type(e).__name__}: {str(e)[:300]}")

# --- VIX3M (3-month implied vol, formerly VXV) ---
try:
    vxv_sym = qb.add_data(CBOE, "VIX3M", Resolution.DAILY)
    vxv_hist = qb.history(vxv_sym.symbol, START, END, Resolution.DAILY)

    if vxv_hist is not None and len(vxv_hist) > 0:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["date", "vxv_close"])
        count = 0
        for idx, row in vxv_hist.iterrows():
            dt = str(idx[1])[:10] if isinstance(idx, tuple) else str(idx)[:10]
            w.writerow([dt, f"{row['close']:.2f}"])
            count += 1
        vxv_csv = buf.getvalue()
        print(f"VIX3M: {count:,} rows, range {str(vxv_hist.index[0])[:10]} -> {str(vxv_hist.index[-1])[:10]}")
    else:
        print("VIX3M: No data returned!")
        # Fallback: try legacy ticker "VXV"
        print("Trying legacy ticker 'VXV'...")
        try:
            vxv_sym2 = qb.add_data(CBOE, "VXV", Resolution.DAILY)
            vxv_hist2 = qb.history(vxv_sym2.symbol, START, END, Resolution.DAILY)
            if vxv_hist2 is not None and len(vxv_hist2) > 0:
                buf = io.StringIO()
                w = csv.writer(buf)
                w.writerow(["date", "vxv_close"])
                count = 0
                for idx, row in vxv_hist2.iterrows():
                    dt = str(idx[1])[:10] if isinstance(idx, tuple) else str(idx)[:10]
                    w.writerow([dt, f"{row['close']:.2f}"])
                    count += 1
                vxv_csv = buf.getvalue()
                print(f"VXV (legacy): {count:,} rows")
            else:
                print("VXV (legacy): No data returned either!")
        except Exception as e2:
            print(f"VXV fallback ERROR: {type(e2).__name__}: {str(e2)[:300]}")

except Exception as e:
    print(f"VIX3M ERROR: {type(e).__name__}: {str(e)[:300]}")

# --- Also build a merged IVTS CSV for convenience ---
ivts_csv = None
if vix_csv and vxv_csv:
    # Parse both into dicts
    vix_dict = {}
    for line in vix_csv.strip().split("\n")[1:]:
        parts = line.split(",")
        vix_dict[parts[0]] = parts[1]

    vxv_dict = {}
    for line in vxv_csv.strip().split("\n")[1:]:
        parts = line.split(",")
        vxv_dict[parts[0]] = parts[1]

    # Merge on date
    all_dates = sorted(set(vix_dict.keys()) & set(vxv_dict.keys()))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "vix_close", "vxv_close", "ivts"])
    for dt in all_dates:
        v = float(vix_dict[dt])
        x = float(vxv_dict[dt])
        ivts = v / x if x > 0 else ""
        w.writerow([dt, f"{v:.2f}", f"{x:.2f}", f"{ivts:.4f}" if ivts else ""])
    ivts_csv = buf.getvalue()
    print(f"IVTS merged: {len(all_dates):,} rows with both VIX and VXV")

# ── Output compressed data ────────────────────────────────────────────────────
print()
print("=" * 60)
print("COMPRESSED OUTPUT — copy everything below")
print("=" * 60)

if vix_csv:
    print_compressed("vix_daily_close.csv", vix_csv)
    print()

if vxv_csv:
    print_compressed("vxv_daily_close.csv", vxv_csv)
    print()

if ivts_csv:
    print_compressed("ivts_daily.csv", ivts_csv)
    print()

print("=" * 60)
files_done = sum(1 for x in [vix_csv, vxv_csv, ivts_csv] if x)
print(f"DONE — {files_done}/3 files extracted")
print("=" * 60)
