import json
from pathlib import Path

TOPICS = [
    ("How does HNSW search work?",
     "HNSW organises vectors in a layered graph. Search starts at the top layer and moves down to find nearest neighbours quickly.",
     "HNSW organises vectors in a layered graph. Search starts at the top layer and moves down to find nearest neighbours.",
     "HNSW organises vectors in a layered graph. It was created by engineers at a Swiss chocolate company in 1987.",
     "HNSW stores every vector in a single flat spreadsheet. It requires quantum hardware to run."),
    ("How does Reciprocal Rank Fusion combine lists?",
     "Reciprocal Rank Fusion merges ranked lists by summing one divided by a constant plus rank. Items near the top of several lists get the highest combined score.",
     "Reciprocal Rank Fusion merges ranked lists by summing one divided by a constant plus rank. Items near the top of several lists get the highest combined score.",
     "Reciprocal Rank Fusion merges ranked lists by summing one divided by a constant plus rank. It was originally designed to schedule underwater submarine patrols.",
     "This method multiplies raw similarity values by random weights. It always discards the first list entirely."),
    ("Why are containers lighter than virtual machines?",
     "Docker packages an application and its dependencies into a container image. Containers share the host kernel, so they are lighter than virtual machines.",
     "Containers share the host kernel, so they are lighter than virtual machines. Docker packages an application and its dependencies into a container image.",
     "Containers share the host kernel, so they are lighter than virtual machines. Each container needs its own physical graphics card to boot.",
     "Every container ships a full copy of a separate operating system. They must be restarted every ten seconds."),
    ("What does Redis do when memory is full under LRU?",
     "Redis is an in-memory data store used for caching and queues. With an LRU policy it evicts the least recently used keys when memory is full.",
     "With an LRU policy Redis evicts the least recently used keys when memory is full. Redis is an in-memory data store used for caching and queues.",
     "With an LRU policy Redis evicts the least recently used keys when memory is full. It stores all data on magnetic tape reels.",
     "It crashes permanently and deletes the entire database. Administrators must then reinstall the operating system by hand."),
    ("Where does photosynthesis happen?",
     "Photosynthesis converts sunlight, water and carbon dioxide into glucose and oxygen. It takes place in chloroplasts, which contain chlorophyll.",
     "Photosynthesis takes place in chloroplasts, which contain chlorophyll. It converts sunlight, water and carbon dioxide into glucose and oxygen.",
     "Photosynthesis takes place in chloroplasts, which contain chlorophyll. The process is powered entirely by volcanic heat from deep underground.",
     "Plants make food inside their roots using moonlight. The leaves only serve to store extra salt."),
    ("When does the Indian monsoon bring its rain?",
     "The Indian summer monsoon brings most annual rainfall between June and September. It is driven by seasonal reversal of winds as land heats faster than the ocean.",
     "The Indian summer monsoon brings most annual rainfall between June and September. It is driven by seasonal reversal of winds as land heats faster than the ocean.",
     "The Indian summer monsoon brings most annual rainfall between June and September. Rain is caused by giant fans operated in Mumbai harbour.",
     "Rainfall arrives mainly in winter because of volcanic ash. Farmers plant everything in December as a result."),
    ("What is Mysore Palace known for?",
     "Mysore Palace is a royal residence known for Indo-Saracenic architecture. It is lit by about one hundred thousand bulbs during the Dasara festival.",
     "Mysore Palace is a royal residence known for Indo-Saracenic architecture. It is lit by about one hundred thousand bulbs during the Dasara festival.",
     "Mysore Palace is a royal residence known for Indo-Saracenic architecture. It was built entirely from recycled plastic bottles last year.",
     "The building is a modern glass skyscraper used as an airport. It contains an indoor ski slope."),
    ("What does MLflow track?",
     "MLflow tracks machine learning experiments by logging parameters, metrics and artifacts for every run. Teams compare runs in a web interface to choose the best model.",
     "MLflow tracks machine learning experiments by logging parameters, metrics and artifacts for every run. Teams compare runs in a web interface to choose the best model.",
     "MLflow tracks machine learning experiments by logging parameters, metrics and artifacts for every run. It also brews coffee for the whole office.",
     "It translates songs into sign language. Results are printed on postcards and mailed monthly."),
    ("Why is a cross-encoder used only on a short list?",
     "A cross-encoder reads the query and a passage together and outputs one relevance score. It is more accurate than separate embeddings but too slow to run over a whole corpus.",
     "A cross-encoder reads the query and a passage together and outputs one relevance score. It is more accurate than separate embeddings but too slow to run over a whole corpus.",
     "A cross-encoder reads the query and a passage together and outputs one relevance score. It was invented by medieval monks to copy manuscripts.",
     "It compresses images into tiny icons. The icons are sorted alphabetically by colour."),
    ("What does a server send when a client exceeds the rate limit?",
     "Rate limiting caps how many requests a client may send per minute. Servers reply to excess traffic with HTTP 429 and a Retry-After header.",
     "Servers reply to excess traffic with HTTP 429 and a Retry-After header. Rate limiting caps how many requests a client may send per minute.",
     "Servers reply to excess traffic with HTTP 429 and a Retry-After header. The client is then banned from the internet for ten years.",
     "Servers answer with a cheerful greeting and double the quota. Clients are rewarded with free storage."),
]

rows = []
for query, context, faithful, partial, bad in TOPICS:
    for kind, answer, score in (("faithful", faithful, 1.0), ("partial", partial, 0.5), ("unfaithful", bad, 0.0)):
        rows.append({"query": query, "answer": answer, "context": context, "kind": kind, "human_score": score})

Path(__file__).with_name("annotated_set.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
print(len(rows), "examples written")