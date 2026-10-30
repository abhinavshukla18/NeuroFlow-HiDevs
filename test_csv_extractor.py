import pandas as pd

from pipelines.ingestion.extractors.csv_extractor import extract_csv


def make(rows):
    pd.DataFrame({
        "id": range(rows),
        "score": [i % 97 for i in range(rows)],
        "city": [["Pune", "Delhi", "Mysore"][i % 3] for i in range(rows)],
    }).to_csv("sample.csv", index=False)


make(250)
pages = extract_csv("sample.csv")
print("small:", [(p.page_number, p.content_type, p.metadata["row_start"], p.metadata["row_end"]) for p in pages])
assert len(pages) == 3 and all(p.content_type == "table" for p in pages)

make(1500)
pages = extract_csv("sample.csv")
print("large:", [(p.page_number, p.content_type, p.metadata["part"]) for p in pages])
print(pages[0].content)
assert len(pages) == 2 and pages[0].content_type == "text"