import json
import os
import math
import streamlit as st
from openai import AzureOpenAI

MASTER_STORE = "backend/glossary_master.json"


def _get_openai_client():
    """Initialize Azure OpenAI client from Streamlit secrets."""
    try:
        endpoint = st.secrets.get("AZURE_OPENAI_ENDPOINT")
        api_key = st.secrets.get("AZURE_OPENAI_API_KEY")
        api_version = st.secrets.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

        if not endpoint or not api_key:
            return None

        return AzureOpenAI(
            azure_endpoint=endpoint.strip(),
            api_key=api_key.strip(),
            api_version=api_version.strip()
        )
    except Exception:
        return None


def _get_embedding_deployment():
    """Return the configured embedding model deployment name."""
    return st.secrets.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")


def _cosine_similarity(vec_a, vec_b):
    """Compute cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _load_glossary_records():
    """Load all records from the glossary master store."""
    if not os.path.exists(MASTER_STORE):
        return []
    try:
        with open(MASTER_STORE, 'r') as f:
            store = json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

    records = []
    for guid, entries in store.items():
        for entry in entries:
            if isinstance(entry, dict) and entry.get("Active") == 1:
                records.append(entry)
    return records


def _build_searchable_text(record):
    """Build a combined text string from a glossary record for embedding."""
    parts = []
    for field in ["Business Term", "Physical Term", "Definition / Description", "table_name", "Type"]:
        val = record.get(field, "")
        if val:
            parts.append(str(val))
    return " | ".join(parts)


def get_embeddings(texts, client=None):
    """Get embeddings for a list of texts using Azure OpenAI."""
    if client is None:
        client = _get_openai_client()
    if client is None:
        return None

    deployment = _get_embedding_deployment()
    try:
        response = client.embeddings.create(
            input=texts,
            model=deployment
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        st.error(f"Embedding API error: {str(e)}")
        return None


def semantic_search_glossary(query, top_k=10, similarity_threshold=0.70):
    """
    Perform semantic search across the glossary master store.

    Args:
        query: Natural language search query
        top_k: Number of top results to return
        similarity_threshold: Minimum cosine similarity to include in results

    Returns:
        List of dicts with record data and similarity scores
    """
    if not query or not query.strip():
        return []

    records = _load_glossary_records()
    if not records:
        return []

    client = _get_openai_client()
    if client is None:
        return []

    # Build searchable texts for all records
    record_texts = [_build_searchable_text(r) for r in records]

    # Get embeddings for the query and all records
    all_texts = [query.strip()] + record_texts
    embeddings = get_embeddings(all_texts, client)

    if embeddings is None or len(embeddings) < 2:
        # Fallback to GPT-based search when embeddings fail
        return _gpt_semantic_search(query, records, record_texts, client, top_k)

    query_embedding = embeddings[0]
    record_embeddings = embeddings[1:]

    # Compute similarities
    results = []
    for i, (record, rec_emb) in enumerate(zip(records, record_embeddings)):
        similarity = _cosine_similarity(query_embedding, rec_emb)
        if similarity >= similarity_threshold:
            results.append({
                "Business Term": record.get("Business Term", ""),
                "Physical Term": record.get("Physical Term", ""),
                "Definition": record.get("Definition / Description", ""),
                "Table": record.get("table_name", ""),
                "Type": record.get("Type", ""),
                "Source": record.get("Source", ""),
                "Confidence (%)": record.get("Confidence (%)", ""),
                "Similarity": round(similarity * 100, 1),
            })

    # Sort by similarity descending
    results.sort(key=lambda x: x["Similarity"], reverse=True)
    return results[:top_k]


def _gpt_semantic_search(query, records, record_texts, client, top_k=10):
    """Use GPT chat completion to rank glossary records by relevance to query."""
    deployment = st.secrets.get("AZURE_OPENAI_DEPLOYMENTNAME", "gpt-4.1")

    # Limit records to avoid token overflow - send max 50 at a time
    indexed_texts = [f"[{i}] {text}" for i, text in enumerate(record_texts[:50])]
    catalog = "\n".join(indexed_texts)

    prompt = f"""You are a glossary search engine. Given a user query and a numbered list of glossary entries, return the indices of the most relevant entries ranked by relevance.

User Query: "{query}"

Glossary Entries:
{catalog}

Return ONLY a JSON array of the top relevant indices (max {top_k}), most relevant first. Example: [3, 7, 12]
If nothing is relevant, return an empty array: []"""

    try:
        response = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=200
        )
        content = response.choices[0].message.content.strip()
        # Parse the JSON array of indices
        indices = json.loads(content)
        if not isinstance(indices, list):
            return []
    except Exception as e:
        st.error(f"Search API error: {str(e)}")
        return keyword_search_glossary(query, top_k)

    results = []
    for rank, idx in enumerate(indices):
        if not isinstance(idx, int) or idx < 0 or idx >= len(records):
            continue
        record = records[idx]
        results.append({
            "Business Term": record.get("Business Term", ""),
            "Physical Term": record.get("Physical Term", ""),
            "Definition": record.get("Definition / Description", ""),
            "Table": record.get("table_name", ""),
            "Type": record.get("Type", ""),
            "Source": record.get("Source", ""),
            "Confidence (%)": record.get("Confidence (%)", ""),
            "Similarity": round((100 - rank * 5), 1),  # Descending relevance score
        })

    return results[:top_k]


def keyword_search_glossary(query, top_k=20):
    """
    Perform keyword-based search across the glossary master store.
    Used as a fallback when embeddings are not available.

    Args:
        query: Search keyword(s)
        top_k: Number of top results to return

    Returns:
        List of matching records
    """
    if not query or not query.strip():
        return []

    records = _load_glossary_records()
    if not records:
        return []

    query_lower = query.strip().lower()
    query_terms = query_lower.split()

    results = []
    for record in records:
        searchable = _build_searchable_text(record).lower()
        # Score based on how many query terms match
        matches = sum(1 for term in query_terms if term in searchable)
        if matches > 0:
            score = matches / len(query_terms)
            results.append({
                "Business Term": record.get("Business Term", ""),
                "Physical Term": record.get("Physical Term", ""),
                "Definition": record.get("Definition / Description", ""),
                "Table": record.get("table_name", ""),
                "Type": record.get("Type", ""),
                "Source": record.get("Source", ""),
                "Confidence (%)": record.get("Confidence (%)", ""),
                "Relevance": round(score * 100, 1),
            })

    results.sort(key=lambda x: x["Relevance"], reverse=True)
    return results[:top_k]
