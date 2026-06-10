"""Qdrant vector store wrapper (lazy-imported).

SCALE's OWN isolated Qdrant — separate container, volume, and collection from any
other project (e.g. parcon). Connection via QDRANT_URL:
  - docker-compose:  http://qdrant:6333 (service name)
  - bare host:       http://localhost:6533 (mapped port, kept off parcon's 6333)
"""

import hashlib
import logging
import os

log = logging.getLogger("cale.vector")

COLLECTION = "scale_concepts"


def _url():
    return os.environ.get("QDRANT_URL", "http://localhost:6533")


def _client():
    from qdrant_client import QdrantClient

    return QdrantClient(url=_url())


def _point_id(rec_id):
    return int(hashlib.md5(rec_id.encode()).hexdigest()[:15], 16)


def ensure_collection(dim, client=None):
    from qdrant_client.models import Distance, VectorParams

    c = client or _client()
    existing = [x.name for x in c.get_collections().collections]
    if COLLECTION not in existing:
        c.create_collection(
            COLLECTION, vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
        )
        log.info("created Qdrant collection %s (dim=%d) at %s", COLLECTION, dim, _url())
    return c


def upsert(records, vectors, client=None):
    from qdrant_client.models import PointStruct

    c = client or _client()
    points = [
        PointStruct(id=_point_id(rec["id"]), vector=vec, payload=rec)
        for rec, vec in zip(records, vectors)
    ]
    c.upsert(COLLECTION, points=points)
    log.info("upserted %d concept vectors", len(points))
    return len(points)


def search(vector, top_k=5, client=None):
    c = client or _client()
    if hasattr(c, "query_points"):  # qdrant-client >= 1.10
        res = c.query_points(COLLECTION, query=vector, limit=top_k, with_payload=True)
        return [(p.score, p.payload) for p in res.points]
    res = c.search(COLLECTION, query_vector=vector, limit=top_k, with_payload=True)  # legacy
    return [(r.score, r.payload) for r in res]
