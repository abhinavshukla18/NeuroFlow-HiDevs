import pandas as pd
from pandas.api.types import is_numeric_dtype

from pipelines.ingestion.extractors import ExtractedPage, rows_to_markdown

SMALL_CSV_MAX_ROWS = 1000
BLOCK_SIZE = 100
SAMPLE_ROWS = 10


def _table(df: pd.DataFrame) -> str:
    rows = [list(df.columns)] + df.astype(object).where(df.notna(), "").values.tolist()
    return rows_to_markdown(rows)


def _summary(df: pd.DataFrame, numeric: list[str], text: list[str]) -> str:
    lines = [f"Dataset summary: {len(df)} rows, {len(df.columns)} columns.", "", "Columns and dtypes:"]
    lines += [f"- {col}: {df[col].dtype}" for col in df.columns]
    if numeric:
        lines += ["", "Numeric columns (min / max / mean):"]
        for col in numeric:
            lines.append(f"- {col}: {df[col].min()} / {df[col].max()} / {df[col].mean():.4g}")
    if text:
        lines += ["", "Text columns (top 5 values):"]
        for col in text:
            top = df[col].value_counts().head(5)
            lines.append(f"- {col}: " + ", ".join(f"{k} ({v})" for k, v in top.items()))
    return "\n".join(lines)


def extract_csv(path: str) -> list[ExtractedPage]:
    df = pd.read_csv(path)
    numeric = [c for c in df.columns if is_numeric_dtype(df[c])]
    text = [c for c in df.columns if c not in numeric]
    base = {"rows": len(df), "numeric_columns": numeric, "text_columns": text}

    if len(df) < SMALL_CSV_MAX_ROWS:
        pages = []
        for number, start in enumerate(range(0, len(df), BLOCK_SIZE), start=1):
            block = df.iloc[start : start + BLOCK_SIZE]
            pages.append(
                ExtractedPage(number, _table(block), "table",
                              {**base, "row_start": start, "row_end": start + len(block) - 1})
            )
        return pages

    return [
        ExtractedPage(1, _summary(df, numeric, text), "text", {**base, "part": "summary"}),
        ExtractedPage(2, _table(df.head(SAMPLE_ROWS)), "table",
                      {**base, "part": "sample", "row_start": 0, "row_end": SAMPLE_ROWS - 1}),
    ]