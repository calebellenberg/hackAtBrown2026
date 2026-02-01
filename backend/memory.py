"""
Memory Engine for ImpulseGuard Slow Brain System

Handles RAG retrieval from Markdown files via ChromaDB, performs reasoning
using Vertex AI (Gemini) via httpx with service account authentication,
and implements self-refining memory updates.
"""

import os
import json
import shutil
from typing import Dict, List, Any, Optional
from datetime import datetime
import asyncio

import chromadb
from chromadb.config import Settings
import httpx
from google.oauth2 import service_account
import google.auth.transport.requests


class MemoryEngine:
    """
    Memory engine that manages RAG retrieval, Vertex AI (Gemini) reasoning via REST API
    with service account authentication, and self-refining memory updates to Markdown files.
    """
    
    SYSTEM_INSTRUCTION = """You are the user's 'Digital Prefrontal Cortex.' Evaluate purchases against their long-term goals and budget. Be rational, protective, and decisive."""

    VERTEX_AI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    
    def __init__(self, memory_dir: str, chroma_persist_dir: str, service_account_path: str):
        """
        Initialize the Memory Engine.
        
        Args:
            memory_dir: Directory containing Markdown memory files
            chroma_persist_dir: Directory for ChromaDB persistent storage
            service_account_path: Path to Google Cloud service account JSON file
        """
        self.memory_dir = memory_dir
        self.chroma_persist_dir = chroma_persist_dir
        self.service_account_path = service_account_path
        
        # Validate service account file exists
        if not os.path.exists(service_account_path):
            raise FileNotFoundError(f"Service account file not found: {service_account_path}")
        
        # Initialize service account credentials
        # Try generative-language scope first, fallback to cloud-platform
        try:
            try:
                self.credentials = service_account.Credentials.from_service_account_file(
                    service_account_path,
                    scopes=['https://www.googleapis.com/auth/generative-language']
                )
            except:
                # Fallback to cloud-platform scope
                self.credentials = service_account.Credentials.from_service_account_file(
                    service_account_path,
                    scopes=['https://www.googleapis.com/auth/cloud-platform']
                )
        except Exception as e:
            raise ValueError(f"Failed to load service account credentials: {e}")
        
        # Initialize ChromaDB
        os.makedirs(chroma_persist_dir, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(
            path=chroma_persist_dir,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Create or get collection
        self.collection = self.chroma_client.get_or_create_collection(
            name="impulseguard_memory",
            metadata={"hnsw:space": "cosine"}
        )
        
        # Track if memory has been indexed
        self._indexed = False
        
        # Track chunk IDs for upsert operations
        self._chunk_ids = {}  # Maps (file_name, section) -> list of chunk IDs
    
    def _get_access_token(self) -> str:
        """
        Get OAuth2 access token from service account credentials.
        
        Returns:
            Access token string
            
        Raises:
            Exception: If token refresh fails
        """
        try:
            # Refresh token if needed
            if not self.credentials.valid:
                request = google.auth.transport.requests.Request()
                self.credentials.refresh(request)
            
            return self.credentials.token
        except Exception as e:
            raise Exception(f"Failed to get access token: {e}")
    
    async def _call_gemini_api(self, prompt: str, system_instruction: Optional[str] = None) -> Dict[str, Any]:
        """
        Call Vertex AI (Gemini) API via REST with OAuth2 authentication and exponential backoff retry logic.
        
        Args:
            prompt: User prompt text
            system_instruction: Optional system instruction (defaults to class constant)
            
        Returns:
            Parsed JSON response from Vertex AI
            
        Raises:
            Exception: If all retries fail
        """
        if system_instruction is None:
            system_instruction = self.SYSTEM_INSTRUCTION
        
        url = self.VERTEX_AI_URL
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {"responseMimeType": "application/json"}
        }
        
        # Exponential backoff: 1s, 2s, 4s, 8s, 16s (max 5 retries)
        delays = [1, 2, 4, 8, 16]
        last_exception = None
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt, delay in enumerate(delays):
                try:
                    # Get OAuth2 access token
                    access_token = self._get_access_token()
                    
                    # Prepare headers with Bearer token
                    headers = {
                        'Authorization': f'Bearer {access_token}',
                        'Content-Type': 'application/json'
                    }
                    
                    response = await client.post(url, json=payload, headers=headers)
                    
                    # Check for specific error codes and provide helpful messages
                    if response.status_code == 403:
                        error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                        error_info = error_data.get('error', {})
                        details = error_info.get('details', [])
                        
                        for detail in details:
                            if detail.get('@type') == 'type.googleapis.com/google.rpc.ErrorInfo':
                                reason = detail.get('reason', '')
                                if reason == 'SERVICE_DISABLED':
                                    activation_url = detail.get('metadata', {}).get('activationUrl', '')
                                    raise ValueError(
                                        f"Generative Language API is not enabled. "
                                        f"Enable it at: {activation_url}"
                                    )
                                elif reason == 'ACCESS_TOKEN_SCOPE_INSUFFICIENT':
                                    raise ValueError(
                                        f"Service account has insufficient permissions. "
                                        f"Ensure it has 'Vertex AI User' or 'Generative Language API User' role."
                                    )
                                elif reason == 'PERMISSION_DENIED':
                                    raise ValueError(
                                        f"Permission denied. Check service account permissions in IAM."
                                    )
                        
                        # Generic 403 error
                        raise ValueError(
                            f"403 Forbidden: {error_info.get('message', 'Access denied')}. "
                            f"Check service account permissions and API enablement."
                        )
                    
                    response.raise_for_status()
                    
                    result = response.json()
                    
                    # Extract text from response
                    if 'candidates' in result and len(result['candidates']) > 0:
                        candidate = result['candidates'][0]
                        if 'content' in candidate and 'parts' in candidate['content']:
                            text = candidate['content']['parts'][0].get('text', '')
                            
                            # Parse JSON response
                            try:
                                return json.loads(text)
                            except json.JSONDecodeError:
                                # Try to extract JSON from markdown code blocks
                                if '```json' in text:
                                    json_start = text.find('```json') + 7
                                    json_end = text.find('```', json_start)
                                    text = text[json_start:json_end].strip()
                                elif '```' in text:
                                    json_start = text.find('```') + 3
                                    json_end = text.find('```', json_start)
                                    text = text[json_start:json_end].strip()
                                
                                return json.loads(text)
                    
                    raise ValueError("Invalid response format from Vertex AI API")
                    
                except (httpx.HTTPError, httpx.RequestError, ValueError, json.JSONDecodeError, Exception) as e:
                    last_exception = e
                    if attempt < len(delays) - 1:
                        await asyncio.sleep(delay)
                    else:
                        raise last_exception
        
        raise last_exception if last_exception else Exception("Failed to call Vertex AI API")
    
    def _chunk_markdown(self, content: str, file_name: str) -> List[Dict[str, Any]]:
        """
        Split Markdown content into embeddable chunks.
        
        Args:
            content: Markdown file content
            file_name: Name of the source file
            
        Returns:
            List of chunk dictionaries with content and metadata
        """
        chunks = []
        lines = content.split('\n')
        current_chunk = []
        current_section = "Introduction"
        
        for line in lines:
            # Detect section headers
            if line.startswith('#'):
                # Save previous chunk if it has content
                if current_chunk:
                    chunk_text = '\n'.join(current_chunk).strip()
                    if chunk_text:
                        chunks.append({
                            'content': chunk_text,
                            'file': file_name,
                            'section': current_section
                        })
                    current_chunk = []
                
                # Extract section name
                current_section = line.lstrip('#').strip()
            else:
                current_chunk.append(line)
        
        # Add final chunk
        if current_chunk:
            chunk_text = '\n'.join(current_chunk).strip()
            if chunk_text:
                chunks.append({
                    'content': chunk_text,
                    'file': file_name,
                    'section': current_section
                })
        
        return chunks
    
    async def reindex_memory(self) -> bool:
        """
        Read all Markdown files and rebuild ChromaDB collection.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Clear existing collection
            try:
                self.chroma_client.delete_collection("impulseguard_memory")
            except:
                pass
            
            self.collection = self.chroma_client.create_collection(
                name="impulseguard_memory",
                metadata={"hnsw:space": "cosine"}
            )
            
            # Reset chunk ID tracking
            self._chunk_ids = {}
            
            # Read all Markdown files
            md_files = ['Goals.md', 'Budget.md', 'State.md', 'Behavior.md']
            all_chunks = []
            all_ids = []
            all_metadatas = []
            
            for md_file in md_files:
                file_path = os.path.join(self.memory_dir, md_file)
                if not os.path.exists(file_path):
                    continue
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                chunks = self._chunk_markdown(content, md_file)
                
                # Track chunk IDs for this file
                file_chunk_ids = []
                
                for i, chunk in enumerate(chunks):
                    chunk_id = f"{md_file}_{i}"
                    file_chunk_ids.append(chunk_id)
                    all_ids.append(chunk_id)
                    all_chunks.append(chunk['content'])
                    all_metadatas.append({
                        'file': chunk['file'],
                        'section': chunk['section']
                    })
                
                # Store chunk IDs for this file
                self._chunk_ids[md_file] = file_chunk_ids
            
            # Add to ChromaDB
            if all_chunks:
                self.collection.add(
                    ids=all_ids,
                    documents=all_chunks,
                    metadatas=all_metadatas
                )
            
            self._indexed = True
            return True
            
        except Exception as e:
            print(f"Error reindexing memory: {e}")
            return False
    
    async def retrieve_context(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context snippets from ChromaDB.
        
        Args:
            query: Query text (typically purchase data description)
            n_results: Number of results to return
            
        Returns:
            List of relevant snippets with metadata
        """
        try:
            if not self._indexed or self.collection.count() == 0:
                await self.reindex_memory()
            
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            snippets = []
            if results['documents'] and len(results['documents']) > 0:
                for i, doc in enumerate(results['documents'][0]):
                    snippet = {
                        'content': doc,
                        'file': results['metadatas'][0][i].get('file', 'unknown'),
                        'section': results['metadatas'][0][i].get('section', 'unknown')
                    }
                    snippets.append(snippet)
            
            return snippets
            
        except Exception as e:
            print(f"Error retrieving context: {e}")
            return []
    
    async def reason_with_gemini(
        self,
        p_impulse_fast: float,
        purchase_data: Dict[str, Any],
        context_snippets: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Perform reasoning using Vertex AI (Gemini) REST API.
        
        Args:
            p_impulse_fast: Fast Brain probability score
            purchase_data: Purchase information (product, cost, website)
            context_snippets: Retrieved context from ChromaDB
            
        Returns:
            Dictionary with reasoning, confidence, intervention action, and optional memory_update
        """
        try:
            # Build context from snippets
            context_text = "\n\n".join([
                f"From {s['file']} ({s['section']}):\n{s['content']}"
                for s in context_snippets
            ])
            
            # Build prompt
            prompt = f"""Analyze this purchase decision:

Fast Brain Impulse Score: {p_impulse_fast:.3f} (0.0 = no impulse, 1.0 = high impulse)

Purchase Details:
- Product: {purchase_data.get('product', 'Unknown')}
- Cost: ${purchase_data.get('cost', 0):.2f}
- Website: {purchase_data.get('website', 'Unknown')}

Relevant Context from User's Memory:
{context_text if context_snippets else "No relevant context found."}

Please provide:
1. A final impulse score (0.0-1.0) considering both the Fast Brain score and the context
2. Your confidence in this assessment (0.0-1.0)
3. A clear reasoning explanation citing specific goals, budget, state, or behavior patterns (e.g., "Violates your $0 gambling limit in Budget.md")
4. An intervention action: "COOLDOWN", "MIRROR", "PHRASE", or "NONE"
5. If this purchase reveals new information about the user, provide a memory_update as a markdown string (e.g., "User is willing to spend $60 on quality apparel"). If no update is needed, set memory_update to null.

Respond in JSON format:
{{
    "impulse_score": <float>,
    "confidence": <float>,
    "reasoning": "<explanation>",
    "intervention_action": "<COOLDOWN|MIRROR|PHRASE|NONE>",
    "memory_update": "<markdown string or null>"
}}"""
            
            # Call Vertex AI API
            result = await self._call_gemini_api(prompt)
            
            # Validate and clamp values
            result['impulse_score'] = max(0.0, min(1.0, float(result.get('impulse_score', p_impulse_fast))))
            result['confidence'] = max(0.0, min(1.0, float(result.get('confidence', 0.5))))
            result['reasoning'] = result.get('reasoning', 'Unable to generate reasoning.')
            
            # Normalize intervention action
            action = result.get('intervention_action', 'NONE').upper()
            if action not in ['COOLDOWN', 'MIRROR', 'PHRASE', 'NONE']:
                action = 'NONE'
            result['intervention_action'] = action
            
            # Handle memory_update (can be null, empty string, or markdown)
            memory_update = result.get('memory_update')
            if memory_update is None or (isinstance(memory_update, str) and memory_update.strip() == ''):
                result['memory_update'] = None
            else:
                result['memory_update'] = str(memory_update).strip()
            
            return result
            
        except Exception as e:
            print(f"Error in Vertex AI reasoning: {e}")
            # Fallback to Fast Brain score
            return {
                'impulse_score': p_impulse_fast,
                'confidence': 0.3,  # Low confidence for fallback
                'reasoning': f'Fast Brain analysis only (Vertex AI unavailable: {str(e)})',
                'intervention_action': 'NONE',
                'memory_update': None
            }
    
    def _determine_target_file(self, memory_update: str) -> str:
        """
        Determine which Markdown file should receive the memory update.
        
        Args:
            memory_update: Memory update content
            
        Returns:
            Target file name (Goals.md, Budget.md, State.md, or Behavior.md)
        """
        update_lower = memory_update.lower()
        
        # Keywords for each file
        if any(kw in update_lower for kw in ['goal', 'objective', 'plan', 'aspiration']):
            return 'Goals.md'
        elif any(kw in update_lower for kw in ['budget', 'spent', 'remaining', 'limit', 'allowance']):
            return 'Budget.md'
        elif any(kw in update_lower for kw in ['balance', 'account', 'income', 'savings', 'wealth', 'financial state']):
            return 'State.md'
        else:
            # Default to Behavior.md for spending patterns, triggers, etc.
            return 'Behavior.md'
    
    async def apply_memory_update(self, memory_update: str) -> bool:
        """
        Apply memory update to the appropriate Markdown file and update ChromaDB.
        
        Args:
            memory_update: Markdown string with new observations
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not memory_update or not memory_update.strip():
                return False
            
            # Determine target file
            target_file = self._determine_target_file(memory_update)
            file_path = os.path.join(self.memory_dir, target_file)
            
            if not os.path.exists(file_path):
                print(f"File not found: {file_path}")
                return False
            
            # Create backup
            backup_path = f"{file_path}.backup"
            shutil.copy2(file_path, backup_path)
            
            try:
                # Read current content
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Append memory update to "Observed Behaviors" or "Recent Changes" section
                # If section doesn't exist, create it
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                update_entry = f"\n- [{timestamp}] {memory_update}"
                
                # Try to find appropriate section
                if "Observed Behaviors" in content:
                    # Append to Observed Behaviors section
                    content = content.replace(
                        "## Observed Behaviors",
                        f"## Observed Behaviors{update_entry}"
                    )
                elif "Recent Changes" in content:
                    # Append to Recent Changes section
                    content = content.replace(
                        "## Recent Changes",
                        f"## Recent Changes{update_entry}"
                    )
                else:
                    # Append as new section
                    content += f"\n\n## Recent Observations{update_entry}"
                
                # Update last updated timestamp
                if "Last Updated" in content:
                    # Replace existing timestamp
                    import re
                    content = re.sub(
                        r'## Last Updated\n- .*',
                        f"## Last Updated\n- {timestamp}",
                        content
                    )
                else:
                    content += f"\n\n## Last Updated\n- {timestamp}"
                
                # Write updated content
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # Update ChromaDB using upsert
                chunks = self._chunk_markdown(content, target_file)
                
                # Get existing chunk IDs for this file
                existing_ids = self._chunk_ids.get(target_file, [])
                
                # Prepare upsert data
                upsert_ids = []
                upsert_documents = []
                upsert_metadatas = []
                
                for i, chunk in enumerate(chunks):
                    chunk_id = f"{target_file}_{i}"
                    upsert_ids.append(chunk_id)
                    upsert_documents.append(chunk['content'])
                    upsert_metadatas.append({
                        'file': chunk['file'],
                        'section': chunk['section']
                    })
                
                # Upsert to ChromaDB
                if upsert_ids:
                    self.collection.upsert(
                        ids=upsert_ids,
                        documents=upsert_documents,
                        metadatas=upsert_metadatas
                    )
                    
                    # Update chunk ID tracking
                    self._chunk_ids[target_file] = upsert_ids
                
                # Remove backup on success
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                
                return True
                
            except Exception as e:
                print(f"Error updating file {file_path}: {e}")
                # Restore backup
                if os.path.exists(backup_path):
                    shutil.copy2(backup_path, file_path)
                    os.remove(backup_path)
                return False
            
        except Exception as e:
            print(f"Error in apply_memory_update: {e}")
            return False
    
    async def analyze_purchase(
        self,
        p_impulse_fast: float,
        purchase_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Main pipeline: retrieve context, reason, update memory.
        
        Args:
            p_impulse_fast: Fast Brain probability score
            purchase_data: Purchase information (product, cost, website)
            
        Returns:
            Structured response with analysis results including memory_update
        """
        # Build query from purchase data
        query = f"{purchase_data.get('product', '')} ${purchase_data.get('cost', 0)} {purchase_data.get('website', '')}"
        
        # Step 1: Retrieve context
        context_snippets = await self.retrieve_context(query, n_results=3)
        
        # Step 2: Reason with Vertex AI
        reasoning = await self.reason_with_gemini(
            p_impulse_fast,
            purchase_data,
            context_snippets
        )
        
        # Step 3: Apply memory update if present
        memory_update = reasoning.get('memory_update')
        if memory_update:
            await self.apply_memory_update(memory_update)
        
        # Return structured response
        return {
            'impulse_score': reasoning['impulse_score'],
            'confidence': reasoning['confidence'],
            'reasoning': reasoning['reasoning'],
            'intervention_action': reasoning['intervention_action'],
            'memory_update': memory_update  # Include in response
        }
