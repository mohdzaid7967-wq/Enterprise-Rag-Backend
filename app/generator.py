from typing import List, Dict, Any
from google import genai
from google.genai import types
from app.config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

RAG_SYSTEM_INSTRUCTION = """You are a helpful, enterprise-grade workplace assistant.
Answer the user's question using ONLY the provided context chunks below.
Strict rules:
1. If the provided context does not contain enough information to answer the question, state: "I cannot find the answer to this question in the provided documentation." Do NOT attempt to guess or hallucinate.
2. Maintain a professional, clear, and direct tone.
3. Base every fact directly on the context provided.
"""

def generate_rag_response(query: str, context_chunks: List[Any]) -> str:
    if not client:
        raise ValueError("GEMINI_API_KEY is not configured in .env.")

    # 1. Format retrieved chunks into structured context
    formatted_context = []
    for idx, chunk in enumerate(context_chunks):
        formatted_context.append(
            f"[Source {idx + 1} | Doc ID: {chunk.document_id}, Page: {chunk.page_number}, Section: {chunk.section}]\n"
            f"{chunk.content}"
        )
    context_str = "\n\n---\n\n".join(formatted_context)

    # 2. Construct user prompt
    prompt = f"""Context documentation:
{context_str}

User Question: {query}
"""

    # 3. Call LLM
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=RAG_SYSTEM_INSTRUCTION,
            temperature=0.2,  # Low temperature for factual precision
        ),
    )
    return response.text or ""