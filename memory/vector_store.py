"""ChromaDB vector store for long-term memory: past reports and source credibility."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import chromadb
from chromadb.config import Settings as ChromaSettings

from config import settings

logger = logging.getLogger(__name__)


class MemoryStore:
    """
    Persistent memory using ChromaDB.

    Two collections:
    - `reports`: Stores past research reports for retrieval and deduplication.
    - `source_credibility`: Tracks source URLs and their credibility over time.
    """

    def __init__(self) -> None:
        self._client: chromadb.ClientAPI | None = None
        self._reports: chromadb.Collection | None = None
        self._credibility: chromadb.Collection | None = None

    def initialize(self) -> None:
        """Initialize the ChromaDB client and collections."""
        self._client = chromadb.PersistentClient(
            path=settings.chroma_persist_directory,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._reports = self._client.get_or_create_collection(
            name="reports",
            metadata={"hnsw:space": "cosine"},
        )
        self._credibility = self._client.get_or_create_collection(
            name="source_credibility",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            f"ChromaDB initialized at {settings.chroma_persist_directory} "
            f"(reports: {self._reports.count()}, credibility: {self._credibility.count()})"
        )

    @property
    def reports(self) -> chromadb.Collection:
        if self._reports is None:
            raise RuntimeError("MemoryStore not initialized. Call initialize() first.")
        return self._reports

    @property
    def credibility(self) -> chromadb.Collection:
        if self._credibility is None:
            raise RuntimeError("MemoryStore not initialized. Call initialize() first.")
        return self._credibility

    # ── Reports ─────────────────────────────────────────────────

    def store_report(
        self,
        report_id: str,
        query: str,
        report: str,
        sources: list[dict],
        conflicts: list[dict],
        critique: dict | None = None,
        iterations: int = 1,
    ) -> None:
        """Store a completed research report."""
        metadata = {
            "query": query,
            "source_count": len(sources),
            "conflict_count": len(conflicts),
            "iterations": iterations,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Store the query as the document (for similarity search)
        # and the full report in metadata
        self.reports.upsert(
            ids=[report_id],
            documents=[query],
            metadatas=[metadata],
        )

        # Store the full report data separately as we can't put large text in metadata
        # ChromaDB metadata has size limits, so store a summary
        logger.info(f"Stored report {report_id} for query: {query[:100]}")

    def get_report(self, report_id: str) -> dict | None:
        """Retrieve a report by ID."""
        try:
            result = self.reports.get(ids=[report_id], include=["documents", "metadatas"])
            if result and result["ids"]:
                return {
                    "id": result["ids"][0],
                    "query": result["documents"][0] if result["documents"] else "",
                    "metadata": result["metadatas"][0] if result["metadatas"] else {},
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get report {report_id}: {e}")
            return None

    def find_similar_queries(self, query: str, n_results: int = 5) -> list[dict]:
        """Find past reports with similar queries."""
        try:
            if self.reports.count() == 0:
                return []
            results = self.reports.query(
                query_texts=[query],
                n_results=min(n_results, self.reports.count()),
                include=["documents", "metadatas", "distances"],
            )
            items = []
            if results and results["ids"] and results["ids"][0]:
                for i, rid in enumerate(results["ids"][0]):
                    items.append({
                        "id": rid,
                        "query": results["documents"][0][i] if results["documents"] else "",
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "distance": results["distances"][0][i] if results["distances"] else 1.0,
                    })
            return items
        except Exception as e:
            logger.error(f"Failed to find similar queries: {e}")
            return []

    def list_reports(self, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        """List all stored reports with pagination."""
        try:
            total = self.reports.count()
            if total == 0:
                return [], 0

            result = self.reports.get(
                include=["documents", "metadatas"],
                limit=limit,
                offset=offset,
            )

            items = []
            if result and result["ids"]:
                for i, rid in enumerate(result["ids"]):
                    meta = result["metadatas"][i] if result["metadatas"] else {}
                    items.append({
                        "id": rid,
                        "query": result["documents"][i] if result["documents"] else "",
                        "metadata": meta,
                    })

            return items, total
        except Exception as e:
            logger.error(f"Failed to list reports: {e}")
            return [], 0

    # ── Source Credibility ──────────────────────────────────────

    def update_credibility(self, url: str, title: str, source_type: str, score: float) -> None:
        """Update credibility information for a source URL."""
        doc_id = url[:512]  # Use URL as ID (truncated)
        try:
            self.credibility.upsert(
                ids=[doc_id],
                documents=[f"{title} ({source_type})"],
                metadatas=[{
                    "url": url[:1000],
                    "title": title[:500],
                    "source_type": source_type,
                    "credibility_score": score,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }],
            )
        except Exception as e:
            logger.error(f"Failed to update credibility for {url}: {e}")

    def get_credibility(self, url: str) -> float | None:
        """Get the stored credibility score for a URL."""
        try:
            result = self.credibility.get(ids=[url[:512]], include=["metadatas"])
            if result and result["ids"] and result["metadatas"]:
                return result["metadatas"][0].get("credibility_score")
            return None
        except Exception:
            return None


# Singleton instance
memory_store = MemoryStore()
