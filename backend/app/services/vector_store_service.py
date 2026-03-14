import re
from typing import List

import chromadb
import httpx
from chromadb import ClientAPI, EmbeddingFunction, Embeddings

from app.config import get_settings
from app.utils.logger import logger

settings = get_settings()

CHUNK_SIZE = 600
CHUNK_OVERLAP = 150


class OllamaEmbeddingFunction(EmbeddingFunction):
    """Ollama embedding API'sini kullanan ChromaDB embedding fonksiyonu."""

    def __init__(self, model: str, base_url: str):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def __call__(self, input: List[str]) -> Embeddings:
        embeddings = []
        for text in input:
            response = httpx.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=60.0,
            )
            response.raise_for_status()
            embeddings.append(response.json()["embedding"])
        return embeddings


class VectorStoreService:
    """ChromaDB tabanlı semantik RAG vector store servisi."""

    def __init__(self):
        self._client: chromadb.ClientAPI | None = None
        self._embedding_fn: OllamaEmbeddingFunction | None = None

    # ------------------------------------------------------------------ helpers

    def _get_client(self) -> ClientAPI:
        if self._client is None:
            self._client = chromadb.PersistentClient(path=settings.chroma_db_path)
        return self._client

    def _get_embedding_fn(self) -> OllamaEmbeddingFunction:
        if self._embedding_fn is None:
            self._embedding_fn = OllamaEmbeddingFunction(
                model=settings.embedding_model,
                base_url=settings.ollama_url,
            )
        return self._embedding_fn

    @staticmethod
    def _safe_name(query_name: str) -> str:
        """Geçerli bir ChromaDB koleksiyon adı üretir (max 63 karakter)."""
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", query_name.lower())
        name = f"entity_{safe}"
        return name[:63]

    @staticmethod
    def _chunk_text(text: str) -> List[str]:
        """Metni örtüşen parçalara böler."""
        if not text or len(text.strip()) < 20:
            return []
        chunks = []
        start = 0
        while start < len(text):
            chunk = text[start : start + CHUNK_SIZE].strip()
            if chunk:
                chunks.append(chunk)
            start += CHUNK_SIZE - CHUNK_OVERLAP
        return chunks

    # ------------------------------------------------------------------ public API

    def index_context(self, query_name: str, context: dict) -> int:
        """
        Context dict'ini ChromaDB'ye indeksler.
        Her yeni aramada eski koleksiyon silinip yeniden oluşturulur.
        Döner: indekslenen chunk sayısı.
        """
        client = self._get_client()
        embedding_fn = self._get_embedding_fn()
        collection_name = self._safe_name(query_name)

        # Eski koleksiyonu temizle
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass

        collection = client.create_collection(
            name=collection_name,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

        sections = {
            "github": context.get("github", ""),
            "social_media": context.get("social_media", ""),
            "web_search": context.get("web_search", ""),
            "deep_context": context.get("deep_context", ""),
        }

        documents, metadatas, ids = [], [], []
        global_idx = 0

        for section_name, text in sections.items():
            if not text:
                continue
            for chunk_i, chunk in enumerate(self._chunk_text(text)):
                documents.append(chunk)
                metadatas.append(
                    {
                        "query_name": query_name,
                        "section": section_name,
                        "chunk_index": chunk_i,
                    }
                )
                ids.append(f"{collection_name}__{section_name}__{global_idx}")
                global_idx += 1

        if not documents:
            logger.log_warning(f"Vector store: '{query_name}' için indekslenecek içerik bulunamadı.")
            return 0

        # ChromaDB batch limiti: 100'er parçada ekle
        batch = 100
        for i in range(0, len(documents), batch):
            collection.add(
                documents=documents[i : i + batch],
                metadatas=metadatas[i : i + batch],
                ids=ids[i : i + batch],
            )

        logger.log_success(
            f"Vector store: '{query_name}' için {global_idx} chunk indekslendi."
        )
        return global_idx

    def search(self, query_name: str, query_text: str, n_results: int = 6) -> str:
        """
        Kullanıcı sorusuna semantik olarak en yakın context chunk'larını döner.
        Koleksiyon bulunamazsa boş string döner (JSON fallback için).
        """
        client = self._get_client()
        embedding_fn = self._get_embedding_fn()
        collection_name = self._safe_name(query_name)

        try:
            collection = client.get_collection(
                name=collection_name,
                embedding_function=embedding_fn,
            )
        except Exception:
            return ""

        total = collection.count()
        if total == 0:
            return ""

        try:
            results = collection.query(
                query_texts=[query_text],
                n_results=min(n_results, total),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.log_warning(f"Vector search hatası: {e}")
            return ""

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        if not docs:
            return ""

        parts = []
        for doc, meta, dist in zip(docs, metas, distances):
            section = meta.get("section", "unknown").upper().replace("_", " ")
            similarity = round(1.0 - dist, 3)
            parts.append(f"[{section} | benzerlik: {similarity}]\n{doc}")

        return "\n\n---\n\n".join(parts)

    def collection_exists(self, query_name: str) -> bool:
        """Verilen sorgu adına ait koleksiyonun varlığını kontrol eder."""
        try:
            self._get_client().get_collection(self._safe_name(query_name))
            return True
        except Exception:
            return False

    def get_chunk_count(self, query_name: str) -> int:
        """Koleksiyondaki toplam chunk sayısını döner."""
        try:
            return self._get_client().get_collection(self._safe_name(query_name)).count()
        except Exception:
            return 0


# Modül düzeyinde singleton
vector_store_service = VectorStoreService()
