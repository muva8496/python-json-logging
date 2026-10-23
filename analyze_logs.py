from pathlib import Path

import pandas as pd

SAMPLE_DIR = Path(__file__).resolve().parent / "sample_logs"

frames = [pd.read_json(path, lines=True) for path in sorted(SAMPLE_DIR.glob("app.log*"))]
df = pd.concat(frames, ignore_index=True)
df["timestamp"] = pd.to_datetime(df["timestamp"])
df = df.sort_values("timestamp").reset_index(drop=True)

print(f"{len(df)} events across {len(frames)} files\n")

print("Events by level")
print(df["level"].value_counts(), "\n")

print("Problems by branch (WARNING and above)")
problems = df[df["level"].isin(["WARNING", "ERROR", "CRITICAL"])]
print(pd.crosstab(problems["branch"].fillna("(none)"), problems["level"]), "\n")

print("Exception types")
exceptions = df["exception"].dropna().apply(lambda e: e["type"])
print(exceptions.value_counts())