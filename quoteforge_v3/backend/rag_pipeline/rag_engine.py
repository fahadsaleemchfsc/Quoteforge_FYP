"""
RAG (Retrieval-Augmented Generation) Engine for QuoteForge
============================================================
Uses ChromaDB as the vector store to retrieve relevant context
(pricing catalogs, legal clauses, product descriptions, historical proposals)
before sending to the LLM for generation.

Architecture:
  1. Knowledge Base → Chunked & Embedded → ChromaDB Vector Store
  2. Query (deal context) → Embedded → Similarity Search → Top-K results
  3. Retrieved Context + Deal Data + Prompt Template → LLM → Generated Section

This ensures AI outputs are GROUNDED in verified data sources,
achieving lower hallucination rates vs unconstrained generation.
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

KNOWLEDGE_BASE_DIR = Path(__file__).parent.parent / "knowledge_base"
CHROMA_DIR = Path(__file__).parent / "chroma_db"


class RAGEngine:
    """Retrieval-Augmented Generation engine using ChromaDB."""

    def __init__(self, persist_dir: str = None):
        self.persist_dir = persist_dir or str(CHROMA_DIR)
        self._client = None
        self._collection = None
        self._embedding_fn = None

    def _get_embedding_function(self):
        """Get the embedding function using sentence-transformers."""
        if self._embedding_fn:
            return self._embedding_fn

        try:
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
            self._embedding_fn = SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
            logger.info("Using sentence-transformers embeddings (all-MiniLM-L6-v2)")
            return self._embedding_fn
        except Exception as e:
            logger.warning(f"Sentence-transformers failed: {e}, using ChromaDB default")
            self._embedding_fn = None
            return None

    def _get_collection(self):
        """Get or create the ChromaDB collection."""
        if self._collection:
            return self._collection

        try:
            import chromadb
        except ImportError:
            logger.error("chromadb not installed. Run: pip install chromadb")
            return None

        self._client = chromadb.PersistentClient(path=self.persist_dir)
        embedding_fn = self._get_embedding_function()

        kwargs = {"name": "quoteforge_knowledge"}
        if embedding_fn:
            kwargs["embedding_function"] = embedding_fn

        self._collection = self._client.get_or_create_collection(**kwargs)
        logger.info(f"ChromaDB collection: {self._collection.count()} documents")
        return self._collection

    def ingest_knowledge_base(self):
        """Load all knowledge base documents into the vector store."""
        collection = self._get_collection()
        if not collection:
            return

        KNOWLEDGE_BASE_DIR.mkdir(exist_ok=True)

        # Create default knowledge base files if they don't exist
        self._ensure_knowledge_base()

        documents = []
        metadatas = []
        ids = []
        doc_id = 0

        for file_path in sorted(KNOWLEDGE_BASE_DIR.glob("*.json")):
            try:
                data = json.loads(file_path.read_text())
                for item in data if isinstance(data, list) else [data]:
                    content = item.get("content", "")
                    if not content:
                        continue

                    # Chunk long documents
                    chunks = self._chunk_text(content, max_chars=1000)
                    for i, chunk in enumerate(chunks):
                        doc_id += 1
                        documents.append(chunk)
                        metadatas.append({
                            "source": file_path.stem,
                            "category": item.get("category", "general"),
                            "title": item.get("title", file_path.stem),
                            "chunk_index": i,
                            "region": item.get("region", "global"),
                        })
                        ids.append(f"doc_{doc_id}")
            except Exception as e:
                logger.warning(f"Error loading {file_path}: {e}")

        if documents:
            # Clear existing and re-add
            try:
                existing_ids = collection.get()["ids"]
                if existing_ids:
                    collection.delete(ids=existing_ids)
            except Exception:
                pass

            # Add in batches
            batch_size = 100
            for i in range(0, len(documents), batch_size):
                batch_end = min(i + batch_size, len(documents))
                collection.add(
                    documents=documents[i:batch_end],
                    metadatas=metadatas[i:batch_end],
                    ids=ids[i:batch_end],
                )

            logger.info(f"Ingested {len(documents)} chunks from {doc_id} source documents")
        else:
            logger.warning("No documents found in knowledge base")

    def retrieve(self, query: str, n_results: int = 5, filter_category: str = None) -> List[dict]:
        """Retrieve relevant documents for a query."""
        collection = self._get_collection()
        if not collection or collection.count() == 0:
            return []

        where_filter = None
        if filter_category:
            where_filter = {"category": filter_category}

        try:
            results = collection.query(
                query_texts=[query],
                n_results=min(n_results, collection.count()),
                where=where_filter,
            )
        except Exception as e:
            logger.error(f"RAG retrieval failed: {e}")
            return []

        retrieved = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results.get("distances") else 0
                retrieved.append({
                    "content": doc,
                    "metadata": meta,
                    "relevance_score": 1 - distance,  # Convert distance to similarity
                })

        return retrieved

    def retrieve_for_section(self, section: str, deal_context: dict) -> str:
        """Retrieve relevant context for a specific proposal section."""
        # Build section-specific query
        queries = {
            "Cover Letter": f"professional cover letter {deal_context.get('industry', '')} {deal_context.get('client_name', '')}",
            "Scope": f"scope of work deliverables timeline {deal_context.get('deal_name', '')}",
            "Pricing": f"pricing terms payment schedule {deal_context.get('region', '')} tax discount",
            "Deliverables": f"deliverables acceptance criteria {deal_context.get('deal_name', '')}",
            "Terms": f"terms conditions compliance {deal_context.get('region', '')} {deal_context.get('compliance_framework', '')}",
            "Summary": f"executive summary value proposition {deal_context.get('industry', '')}",
        }

        query = queries.get(section, f"{section} proposal content")

        # Add deal-specific context to query
        query += f" {deal_context.get('client_name', '')} {deal_context.get('deal_name', '')}"

        # Category mapping
        category_map = {
            "Cover Letter": None,
            "Scope": None,
            "Pricing": "pricing",
            "Deliverables": None,
            "Terms": "compliance",
            "Summary": None,
        }

        results = self.retrieve(query, n_results=3, filter_category=category_map.get(section))

        if not results:
            return ""

        # Format retrieved context
        context_parts = []
        for r in results:
            source = r["metadata"].get("title", "unknown")
            context_parts.append(f"[Source: {source}]\n{r['content']}")

        return "\n\n---\n\n".join(context_parts)

    @staticmethod
    def _chunk_text(text: str, max_chars: int = 1000) -> List[str]:
        """Split text into chunks, respecting paragraph boundaries."""
        if len(text) <= max_chars:
            return [text]

        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 <= max_chars:
                current_chunk += ("\n\n" + para if current_chunk else para)
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks if chunks else [text[:max_chars]]

    def _ensure_knowledge_base(self):
        """Create default knowledge base files if none exist."""
        if list(KNOWLEDGE_BASE_DIR.glob("*.json")):
            return  # Already has files

        # ─── Compliance Knowledge ─────────────────────────
        compliance_data = [
            {
                "title": "SOC 2 Type II Requirements",
                "category": "compliance",
                "region": "US",
                "content": (
                    "SOC 2 Type II Compliance Requirements for Service Organizations:\n\n"
                    "Security: Information and systems are protected against unauthorized access. "
                    "Controls include firewalls, intrusion detection, multi-factor authentication, "
                    "and encryption (AES-256 at rest, TLS 1.3 in transit).\n\n"
                    "Availability: Systems are available for operation and use as committed. "
                    "Includes disaster recovery, business continuity planning, and 99.9% uptime SLAs.\n\n"
                    "Processing Integrity: System processing is complete, valid, accurate, timely, "
                    "and authorized. Quality assurance and monitoring controls are in place.\n\n"
                    "Confidentiality: Information designated as confidential is protected as committed. "
                    "Data classification, access controls, and secure disposal procedures implemented.\n\n"
                    "Privacy: Personal information is collected, used, retained, disclosed, and disposed "
                    "in conformity with the entity's privacy notice and AICPA privacy criteria."
                ),
            },
            {
                "title": "GDPR Data Protection Requirements",
                "category": "compliance",
                "region": "EU",
                "content": (
                    "GDPR Compliance Framework (Regulation EU 2016/679):\n\n"
                    "Lawfulness: Data processing must have a legal basis (consent, contract, "
                    "legitimate interest, legal obligation, vital interest, or public task).\n\n"
                    "Data Minimization: Only collect and process data that is strictly necessary "
                    "for the specified purpose. Avoid excessive data collection.\n\n"
                    "Purpose Limitation: Personal data must be collected for specified, explicit, "
                    "and legitimate purposes and not further processed incompatibly.\n\n"
                    "Storage Limitation: Personal data should only be kept for as long as necessary "
                    "to fulfill its purpose. Implement data retention policies.\n\n"
                    "Data Subject Rights: Right to access, rectification, erasure (right to be forgotten), "
                    "data portability, restriction of processing, and objection to processing.\n\n"
                    "Data Processing Agreement (DPA): Required between data controllers and processors. "
                    "Must specify processing details, security measures, and sub-processor policies.\n\n"
                    "Breach Notification: Data breaches must be reported to supervisory authority "
                    "within 72 hours. Affected individuals must be notified without undue delay."
                ),
            },
            {
                "title": "PPRA Pakistan Procurement Rules",
                "category": "compliance",
                "region": "PK",
                "content": (
                    "PPRA Rules 2004 — Public Procurement Regulatory Authority of Pakistan:\n\n"
                    "Transparency: All procurement processes must be transparent and documented. "
                    "Bid evaluations must follow predefined, published criteria.\n\n"
                    "Open Competition: Procurement above PKR 100,000 requires competitive bidding. "
                    "Single-source procurement only permitted under specific exemptions.\n\n"
                    "Economy: Procuring agencies must ensure value for money. Price reasonableness "
                    "must be documented and justified.\n\n"
                    "Rule of Consistency: Rules of the procurement process must be applied consistently "
                    "to all bidders. No discrimination or preferential treatment.\n\n"
                    "Tax Compliance: All vendors must be registered taxpayers. GST at 17% is applicable "
                    "on goods and services. Withholding tax provisions apply as per FBR rules.\n\n"
                    "Documentation: Complete procurement record must be maintained for audit purposes. "
                    "Includes bid documents, evaluation reports, contract awards, and performance records.\n\n"
                    "Grievance Mechanism: Bidders have the right to file complaints with PPRA. "
                    "Grievances must be addressed within the prescribed timeline."
                ),
            },
        ]

        # ─── Pricing Knowledge ────────────────────────────
        pricing_data = [
            {
                "title": "Enterprise Pricing Best Practices",
                "category": "pricing",
                "region": "global",
                "content": (
                    "Enterprise Software Pricing Guidelines:\n\n"
                    "Volume Discounts: Standard tiers are 5% for 50+ units, 10% for 100+ units, "
                    "15% for enterprise agreements above $50,000, and 20% for multi-year commitments.\n\n"
                    "Payment Terms: Standard is Net 30. Enterprise clients may negotiate Net 45 or Net 60. "
                    "Early payment discount of 2% for payment within 10 days (2/10 Net 30).\n\n"
                    "Subscription Pricing: Annual billing provides 15-20% savings over monthly billing. "
                    "Multi-year contracts (3-5 years) can include price lock guarantees.\n\n"
                    "Implementation Fees: Typically 15-25% of total license value. Includes setup, "
                    "configuration, data migration, and initial training. Should be quoted separately.\n\n"
                    "Support Tiers: Basic (business hours, email) included. Premium (24/7, phone) "
                    "is 15-20% of annual license fee. Enterprise (dedicated CSM) is 20-25%."
                ),
            },
            {
                "title": "Regional Tax Rates",
                "category": "pricing",
                "region": "global",
                "content": (
                    "Applicable Tax Rates by Region:\n\n"
                    "United States: Sales tax varies by state (0-10.25%). No federal sales tax. "
                    "Software-as-a-Service taxability varies by state. Average effective rate: 7.5%.\n\n"
                    "European Union: VAT rates range from 17% (Luxembourg) to 27% (Hungary). "
                    "Standard rates: Germany 19%, France 20%, UK 20%, Netherlands 21%, Italy 22%.\n\n"
                    "Pakistan: General Sales Tax (GST) is 17% on goods and services. "
                    "Withholding tax provisions apply per FBR Income Tax Ordinance 2001. "
                    "IT services may qualify for reduced rates under IT/ITeS exemptions.\n\n"
                    "Canada: GST 5% federal + provincial sales tax varies (0-10%). HST in some provinces.\n\n"
                    "Note: All tax calculations should be validated against current legislation. "
                    "QuoteForge applies configured tax rules; final liability determined by tax advisors."
                ),
            },
        ]

        # ─── Product & Industry Knowledge ─────────────────
        product_data = [
            {
                "title": "SaaS Platform Proposal Template",
                "category": "product",
                "region": "global",
                "content": (
                    "Standard SaaS Platform Engagement Structure:\n\n"
                    "Phase 1 — Discovery (1-2 weeks): Requirements gathering, stakeholder interviews, "
                    "current state assessment, gap analysis, success criteria definition.\n\n"
                    "Phase 2 — Design (2-3 weeks): Solution architecture, integration design, "
                    "data migration plan, security review, compliance mapping.\n\n"
                    "Phase 3 — Build (4-6 weeks): Platform configuration, custom development, "
                    "integration implementation, data migration execution.\n\n"
                    "Phase 4 — Test (2 weeks): Functional testing, integration testing, "
                    "user acceptance testing, performance testing, security validation.\n\n"
                    "Phase 5 — Deploy (1-2 weeks): Production deployment, cutover execution, "
                    "monitoring setup, user training, operational handover.\n\n"
                    "Phase 6 — Support (ongoing): Warranty period (90 days), transition to "
                    "steady-state support, quarterly business reviews, optimization recommendations."
                ),
            },
            {
                "title": "Government Procurement Proposal Guidelines",
                "category": "product",
                "region": "PK",
                "content": (
                    "Guidelines for Pakistan Government Procurement Proposals:\n\n"
                    "Structure: Technical proposal and financial proposal must be submitted separately "
                    "in sealed envelopes (QCBS method - Quality and Cost Based Selection).\n\n"
                    "Technical Proposal Must Include: Company profile, team qualifications, "
                    "methodology, work plan, timeline, past performance references (minimum 3 similar "
                    "projects), compliance declarations.\n\n"
                    "Financial Proposal Must Include: Detailed cost breakdown by deliverable, "
                    "all applicable taxes clearly stated, payment schedule linked to milestones, "
                    "validity period (minimum 90 days).\n\n"
                    "Evaluation Criteria: Technical (typically 70-80%) and Financial (20-30%). "
                    "Technical minimum qualifying score is usually 70/100.\n\n"
                    "Required Certifications: NTN (National Tax Number), STRN (Sales Tax Registration), "
                    "PEC registration (for engineering firms), active bank account details."
                ),
            },
        ]

        # Write knowledge base files
        for name, data in [
            ("compliance_frameworks", compliance_data),
            ("pricing_guidelines", pricing_data),
            ("product_templates", product_data),
        ]:
            path = KNOWLEDGE_BASE_DIR / f"{name}.json"
            path.write_text(json.dumps(data, indent=2))
            logger.info(f"Created knowledge base: {path.name}")


# ─── Module-level functions for easy import ───────────────────────

_engine = None


def get_rag_engine() -> RAGEngine:
    """Get singleton RAG engine instance."""
    global _engine
    if _engine is None:
        _engine = RAGEngine()
    return _engine


def initialize_rag():
    """Initialize and populate the RAG vector store."""
    engine = get_rag_engine()
    engine.ingest_knowledge_base()
    return engine


def retrieve_context(section: str, deal_context: dict) -> str:
    """Retrieve relevant context for a proposal section."""
    engine = get_rag_engine()
    return engine.retrieve_for_section(section, deal_context)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Initializing RAG Engine...")
    engine = initialize_rag()
    print(f"\nVector store contains {engine._get_collection().count()} documents")

    # Test retrieval
    print("\n" + "=" * 60)
    print("Test Query: SOC 2 compliance for US enterprise deal")
    results = engine.retrieve("SOC 2 compliance requirements for enterprise software", n_results=3)
    for r in results:
        print(f"\n  [{r['metadata'].get('title', 'unknown')}] (score: {r['relevance_score']:.3f})")
        print(f"  {r['content'][:150]}...")

    print("\n" + "=" * 60)
    print("Test Query: PPRA Pakistan government procurement")
    results = engine.retrieve("PPRA procurement rules Pakistan government", n_results=3)
    for r in results:
        print(f"\n  [{r['metadata'].get('title', 'unknown')}] (score: {r['relevance_score']:.3f})")
        print(f"  {r['content'][:150]}...")
