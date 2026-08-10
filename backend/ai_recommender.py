import streamlit as st
import json
import time
import pandas as pd
import sys
import os
from openai import AzureOpenAI

def get_openai_client():
    """Initialize Azure OpenAI client from Streamlit secrets"""
    try:
        endpoint   = st.secrets.get("AZURE_OPENAI_ENDPOINT")
        api_key    = st.secrets.get("AZURE_OPENAI_API_KEY")
        api_version = st.secrets.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

        if not endpoint or not api_key:
            st.error("⚠️ AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_API_KEY not found in Streamlit secrets (.streamlit/secrets.toml)")
            return None

        client = AzureOpenAI(
            azure_endpoint=endpoint.strip(),
            api_key=api_key.strip(),
            api_version=api_version.strip()
        )
        return client
    except Exception as e:
        st.error(f"Error initializing Azure OpenAI client: {str(e)}")
        return None

def _deployment():
    """Return the configured Azure deployment name."""
    return st.secrets.get("AZURE_OPENAI_DEPLOYMENTNAME", "gpt-4.1")

def _max_tokens():
    """Return the configured max tokens."""
    return int(st.secrets.get("MAX_TOKENS", 16384))

# ============================================
# AI RECOMMENDATION LOGIC
# ============================================

def generate_cde_suggestions(business_requirement, industry="General", file_columns=None):
    """Generate CDE suggestions using OpenAI"""
    client = get_openai_client()
    if not client: return []
    
    context_part = f"Industry Context: {industry}\n"
    if file_columns:
        context_part += f"Target Dataset Columns: {', '.join(file_columns)}\n"
        task_instruction = "Task: Analyze the provided dataset columns and the business requirement. Identify which of these columns (or other missing elements) are Critical Data Elements."
    else:
        task_instruction = "Task: Identify 3-5 potential CDEs that are relevant to this requirement."

    prompt = f"""You are a data governance expert in the {industry} industry. 
    Context: {context_part}
    Business Requirement: "{business_requirement}"
    {task_instruction}
    
    For each CDE, provide name, domain, definition, and rationale.
    Respond ONLY with a JSON array."""
    
    try:
        response = client.chat.completions.create(
            model=_deployment(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=_max_tokens()
        )
        
        response_text = response.choices[0].message.content
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
            
        return json.loads(response_text)
    except Exception as e:
        st.error(f"❌ Error generating AI suggestions: {str(e)}")
        return []

def recommend_cdes_from_columns(table_name, columns, industry="General"):
    """Specifically recommend CDEs based on a table schema"""
    client = get_openai_client()
    if not client: return []
    
    prompt = f"Identify 3-5 CDEs for table '{table_name}' with columns: {', '.join(columns)}. Industry: {industry}. Respond ONLY with JSON array."
    
    try:
        response = client.chat.completions.create(
            model=_deployment(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=_max_tokens()
        )
        text = response.choices[0].message.content
        if "```json" in text: text = text.split("```json")[1].split("```")[0].strip()
        return json.loads(text)
    except Exception as e:
        st.error(f"❌ AI Error: {str(e)}")
        return []

class AIRecommender:
    def recommend_cdes_from_columns(self, table_name, columns, industry="General"):
        return recommend_cdes_from_columns(table_name, columns, industry)



# ... (middle of the file)

def generate_glossary_suggestions(table_name, columns, industry="General", business_context="", selected_options=None):
    """Generate Glossary suggestions based on user selection"""
    client = get_openai_client()
    if not client: return []
    
    if not selected_options:
        selected_options = ["Business Term", "Column Description"]
        
    instr = []
    fields = ["type", "related_column", "confidence_score"] # Always include identifiers
    
    if "Business Term" in selected_options:
        instr.append("- Suggest a formal Enterprise Business Concept for 'name' (Business Term). Do NOT just expand the column abbreviation. Provide the true business meaning (e.g. use 'Primary Identifier' instead of 'ID', or 'Biological Sex Classification' instead of just 'Gender').")
        fields.append("name")
    if "Business Definition" in selected_options:
        instr.append("- Provide a precise 'definition' (Business Definition/Description)")
        fields.append("description")
    if "Classifications" in selected_options:
        instr.append(
            "- Assign a 'classification' from EXACTLY one of the following categories based on the data sensitivity and nature of the column/table:\n"
            "  * PII (Personally Identifiable Information) - names, emails, phone numbers, addresses\n"
            "  * Sensitive PII - SSN, passport, biometric data, racial/ethnic origin\n"
            "  * PHI (Protected Health Information) - medical records, diagnoses, prescriptions\n"
            "  * Confidential - trade secrets, proprietary algorithms, internal strategies\n"
            "  * Restricted - data with regulatory/legal access controls\n"
            "  * Internal - internal operational data not meant for external sharing\n"
            "  * Public - publicly available or non-sensitive data\n"
            "  Choose the MOST appropriate single classification for each item."
        )
        fields.append("classification")
    

        
    prompt = f"""You are a Data Governance expert. Analyze the table '{table_name}' and its columns: {', '.join(columns)}.
    Context: {business_context}
    Industry: {industry}
    
    Task:
    - First, provide a suggestion for the overall Table.
    - Then, provide a suggestion for each column.
    {chr(10).join(instr)}
    - For 'confidence_score', provide an integer 0-100 reflecting your certainty based on the schema clarity and matching history.
    
    Response Requirements:
    - Respond ONLY with a valid JSON array of objects.
    - Do NOT prefix column terms with the table name (e.g. for table "Patient", use "Date of Birth" instead of "Patient Date of Birth").
    - Each object must contain: {', '.join(fields)}.
    - For the table-level entry, leave 'related_column' empty.
    - For 'type', use 'Table' or 'Column'.
    - Provide NO domain."""
    
    try:
        response = client.chat.completions.create(
            model=_deployment(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=_max_tokens()
        )
        text = response.choices[0].message.content
        if "```json" in text: text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text: text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)
    except json.JSONDecodeError as jde:
        st.error(f"AI generated invalid JSON: {jde}\n\nRaw Text:\n{text}")
        return []
    except Exception as e:
        st.error(f"AI Generation failed: {str(e)}")
        return []
