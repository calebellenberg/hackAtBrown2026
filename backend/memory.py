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
    
    SYSTEM_INSTRUCTION = """You are the user's 'Digital Prefrontal Cortex' - a deliberate, context-aware reasoning system that evaluates purchases based on GENUINE UTILITY and USER CONTEXT.

## CRITICAL: UTILITY EVALUATION (MANDATORY FIRST STEP)

Before making ANY score adjustments, you MUST evaluate the UTILITY of this purchase:

### What is Utility?
Utility means the item serves a **genuine practical purpose** in the user's life. Ask yourself:
- Does this item solve a real problem the user has?
- Does this item fulfill a legitimate need (professional, personal, health, safety)?
- Would a reasonable person in this user's situation need this item?

### Utility Categories (evaluate honestly)

**STRONG UTILITY (reduce score significantly: -0.3 to -0.5)**
- Professional necessities: dress shoes for work, business attire for interviews, laptop for job
- Health/safety needs: medications, safety equipment, ergonomic furniture for chronic pain
- Essential replacements: broken appliance, worn-out shoes that are primary pair
- Goal-aligned tools: running shoes for marathon training, camera for photography career
- Problem-solving: item directly addresses a stated problem or need in memory files

**MODERATE UTILITY (reduce score: -0.15 to -0.25)**
- Quality upgrades: replacing functional but degraded items (old mattress, worn clothing)
- Seasonal necessities: winter coat before winter, umbrella during rainy season
- Hobby equipment: tools for established hobbies (not new impulse hobbies)
- Home improvement: functional improvements (not purely decorative)

**WEAK/NO UTILITY (no reduction or INCREASE score)**
- Duplicate items: buying similar item to one already owned
- Impulse categories: collectibles, limited editions, flash sales, "deals"
- Pure entertainment: gaming, streaming, toys (unless gift or established hobby)
- Status/vanity: luxury items primarily for appearance/status, not function
- Rationalized wants: "I might need this someday" or "it's a good deal"

### CRITICAL UTILITY QUESTIONS

1. **The Replacement Test**: Is this replacing something broken/worn, or adding to existing items?
   - Replacing broken dress shoes = HIGH utility
   - Buying 5th pair of sneakers = LOW utility

2. **The Necessity Test**: Would the user's life be significantly worse without this item?
   - Need dress shoes for job interview tomorrow = HIGH utility
   - Want dress shoes because they look nice = LOW utility

3. **The Timing Test**: Is there urgency, or is this "want it now" impulse?
   - Winter coat in October when old one is torn = HIGH utility
   - Winter coat in July because it's on sale = LOW utility (impulse triggered by sale)

4. **The Specificity Test**: Does the user need THIS specific item, or is the category browsing?
   - Researched specific running shoe model for flat feet = HIGH utility
   - Browsing "shoes" and found these look cool = LOW utility

## REASONING PRIORITY (in order of importance)

1. **UTILITY EVALUATION** (HIGHEST PRIORITY):
   - Apply the utility tests above FIRST
   - Strong utility = significant negative adjustment (-0.3 to -0.5)
   - Weak/no utility = no reduction or positive adjustment (+0.1 to +0.3)
   - BE SKEPTICAL: Most purchases people make are wants, not needs

2. **GOAL ALIGNMENT**:
   - Does this purchase support the user's stated goals in Goals.md?
   - If YES AND has utility → compound the negative adjustment
   - If YES but weak utility → modest negative adjustment only
   - Example: Dress shoes for marathon runner with no job interviews = low utility despite being "nice to have"

3. **BUDGET CONSTRAINTS**:
   - Does this exceed stated limits in Budget.md?
   - High utility items can still violate budget = modest positive adjustment
   - Low utility + over budget = strong positive adjustment

4. **IMPULSE INDICATORS**:
   - Sale/deal language in product name = +0.1 to +0.2 (scarcity triggers impulse)
   - Late night (11 PM - 5 AM) + low utility = +0.1 to +0.2
   - Very fast time-to-cart (<30s) + low utility = +0.1 (didn't research)
   - High scroll velocity + fast decision = browsing/impulse pattern

5. **BEHAVIORAL PATTERNS** (from Behavior.md):
   - Has user shown this is an established need/pattern?
   - Or is this a new category (potential impulse exploration)?

## LUXURY AND HIGH-PRICED ITEMS

**IMPORTANT**: Price alone does NOT determine utility.

- $200 dress shoes for daily work use = HIGH utility (amortized cost is low)
- $200 dress shoes as 4th pair "for variety" = LOW utility
- $500 espresso machine for daily coffee drinker = MODERATE utility
- $500 espresso machine impulse buy = LOW utility

**Ask**: Is this a NEED at this price point, or is the price itself part of the appeal (status/luxury)?

## SCORE CALCULATION

Start with Fast Brain score, then apply adjustments:

| Factor | Adjustment |
|--------|------------|
| Strong utility | -0.3 to -0.5 |
| Moderate utility | -0.15 to -0.25 |
| Weak/no utility | 0 to +0.2 |
| Goal-aligned + utility | Additional -0.1 to -0.2 |
| Budget violation | +0.1 to +0.3 |
| Sale/deal trigger | +0.1 to +0.2 |
| Late night + low utility | +0.1 to +0.2 |
| Fast decision + low utility | +0.1 |

**Final score MUST be in range [0.0, 1.0]**

## INTERVENTION THRESHOLDS

- impulse_score < 0.50: "NONE" (allow purchase)
- impulse_score 0.50-0.70: "MIRROR" (gentle reflection)
- impulse_score 0.70-0.85: "COOLDOWN" (wait period)
- impulse_score > 0.85: "PHRASE" (strong intervention required)

## REASONING OUTPUT REQUIREMENTS

Your reasoning MUST include:
1. Explicit utility evaluation: "This item has [STRONG/MODERATE/WEAK] utility because..."
2. Citation from memory files if relevant
3. Clear score adjustment logic

Example good reasoning:
- "STRONG utility: Dress shoes needed for upcoming job interviews (Goals.md mentions job search). Replacing worn pair. Score reduced significantly."
- "WEAK utility: Fourth pair of sneakers when user owns 3 similar pairs (Behavior.md). Sale price is triggering impulse. Score increased."

## MEMORY UPDATE REQUIREMENTS

Generate memory_update ONLY for genuinely new information:
- New utility patterns: "User has established need for [category] due to [reason]"
- Spending comfort levels: "User comfortable with $X for [category] purchases"
- Impulse triggers: "User susceptible to [sale/late night/category] impulse purchases"

Set to null if no new patterns emerge or this matches existing behavior."""

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
        
        # Exponential backoff: longer delays to avoid rate limiting (2s, 5s, 10s, 20s, 40s)
        delays = [2, 5, 10, 20, 40]
        last_exception = None
        
        async with httpx.AsyncClient(timeout=60.0) as client:  # Increased timeout
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
                    
                    # Handle 429 Too Many Requests with extended backoff
                    if response.status_code == 429:
                        retry_after = int(response.headers.get('Retry-After', delay * 2))
                        print(f"Rate limited (429). Waiting {retry_after}s before retry...")
                        await asyncio.sleep(retry_after)
                        continue  # Retry the request
                    
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
    
    # Maximum characters per chunk to prevent oversized embeddings
    MAX_CHUNK_SIZE = 500

    def _chunk_markdown(self, content: str, file_name: str) -> List[Dict[str, Any]]:
        """
        Split Markdown content into embeddable chunks.

        Chunks are split by section headers, then further split if they exceed
        MAX_CHUNK_SIZE to ensure efficient embedding and retrieval.

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

        def add_chunk(text: str, section: str):
            """Add chunk, splitting if it exceeds MAX_CHUNK_SIZE."""
            text = text.strip()
            if not text:
                return

            if len(text) <= self.MAX_CHUNK_SIZE:
                chunks.append({
                    'content': text,
                    'file': file_name,
                    'section': section
                })
            else:
                # Split large chunks by lines, respecting MAX_CHUNK_SIZE
                chunk_lines = text.split('\n')
                sub_chunk = []
                sub_chunk_len = 0
                part_num = 1

                for line in chunk_lines:
                    line_len = len(line) + 1  # +1 for newline
                    if sub_chunk_len + line_len > self.MAX_CHUNK_SIZE and sub_chunk:
                        chunks.append({
                            'content': '\n'.join(sub_chunk).strip(),
                            'file': file_name,
                            'section': f"{section} (part {part_num})"
                        })
                        sub_chunk = []
                        sub_chunk_len = 0
                        part_num += 1
                    sub_chunk.append(line)
                    sub_chunk_len += line_len

                if sub_chunk:
                    chunks.append({
                        'content': '\n'.join(sub_chunk).strip(),
                        'file': file_name,
                        'section': f"{section} (part {part_num})" if part_num > 1 else section
                    })

        for line in lines:
            # Detect section headers
            if line.startswith('#'):
                # Save previous chunk if it has content
                if current_chunk:
                    add_chunk('\n'.join(current_chunk), current_section)
                    current_chunk = []

                # Extract section name
                current_section = line.lstrip('#').strip()
            else:
                current_chunk.append(line)

        # Add final chunk
        if current_chunk:
            add_chunk('\n'.join(current_chunk), current_section)

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
        Retrieve context from memory files using query-aware retrieval.

        Optimized retrieval strategy:
        1. ALWAYS include Goals.md and Budget.md (critical for decision-making)
        2. Use ChromaDB similarity search for Behavior.md and State.md chunks
        3. This reduces context payload by 40-60% vs dumping all files

        Args:
            query: Query text (typically purchase data description)
            n_results: Number of similarity results to include for Behavior/State

        Returns:
            List of relevant snippets with metadata
        """
        snippets = []

        # Step 1: ALWAYS read Goals.md and Budget.md directly (critical context)
        critical_files = ['Goals.md', 'Budget.md']
        for filename in critical_files:
            filepath = os.path.join(self.memory_dir, filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            snippets.append({
                                'content': content,
                                'file': filename,
                                'section': 'FULL FILE',
                                'source': 'direct_read'
                            })
                except Exception as e:
                    print(f"Error reading {filename}: {e}")

        # Step 2: Use similarity search for Behavior.md and State.md chunks only
        try:
            if not self._indexed or self.collection.count() == 0:
                await self.reindex_memory()

            # Query only Behavior.md and State.md chunks via similarity
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where={"file": {"$in": ["Behavior.md", "State.md"]}}
            )

            if results['documents'] and len(results['documents']) > 0:
                for i, doc in enumerate(results['documents'][0]):
                    snippet = {
                        'content': doc,
                        'file': results['metadatas'][0][i].get('file', 'unknown'),
                        'section': results['metadatas'][0][i].get('section', 'unknown'),
                        'source': 'similarity_search'
                    }
                    snippets.append(snippet)

        except Exception as e:
            print(f"Error in similarity search: {e}")
            # Fallback: read Behavior.md and State.md directly if similarity fails
            fallback_files = ['Behavior.md', 'State.md']
            for filename in fallback_files:
                filepath = os.path.join(self.memory_dir, filename)
                if os.path.exists(filepath):
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read().strip()
                            if content:
                                snippets.append({
                                    'content': content,
                                    'file': filename,
                                    'section': 'FULL FILE',
                                    'source': 'fallback_read'
                                })
                    except Exception as read_e:
                        print(f"Error reading {filename}: {read_e}")

        print(f"[Memory] Retrieved context from {len(snippets)} sources")
        return snippets
    
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
            
            # Extract time of day for late-night detection
            system_hour = purchase_data.get('system_hour', 12)  # Default to noon if not provided
            is_late_night = system_hour >= 23 or system_hour <= 5
            time_risk_label = "LATE NIGHT (11 PM - 5 AM)" if is_late_night else "Normal hours"
            
            product_name = purchase_data.get('product', 'Unknown')
            cost = purchase_data.get('cost', 0)
            website = purchase_data.get('website', 'Unknown')
            
            # Extract telemetry data for behavioral pattern analysis
            time_to_cart = purchase_data.get('time_to_cart', None)
            time_on_site = purchase_data.get('time_on_site', None)
            click_rate = purchase_data.get('click_rate', None)
            peak_scroll_velocity = purchase_data.get('peak_scroll_velocity', None)
            click_count = purchase_data.get('click_count', None)
            # BIOMETRICS_DISABLED: HR and RR no longer extracted
            # heart_rate = purchase_data.get('heart_rate', None)
            # respiration_rate = purchase_data.get('respiration_rate', None)

            # Build telemetry summary for prompt
            # BIOMETRICS_DISABLED: Removed heart_rate and respiration_rate checks
            telemetry_summary = ""
            if (time_to_cart is not None or click_rate is not None or peak_scroll_velocity is not None):
                telemetry_summary = "\n## Behavioral Telemetry (for pattern learning)\n"
                if time_to_cart is not None:
                    telemetry_summary += f"- Time to Cart: {time_to_cart:.1f}s (under 5s = extremely impulsive, 5-30s = rapid, 30-120s = normal, >120s = deliberate)\n"
                if time_on_site is not None:
                    telemetry_summary += f"- Time on Site: {time_on_site:.1f}s\n"
                if click_rate is not None:
                    telemetry_summary += f"- Click Rate: {click_rate:.2f} clicks/sec (only \"high\" if >0.25 clicks/sec; lower is normal)\n"
                if peak_scroll_velocity is not None:
                    telemetry_summary += f"- Peak Scroll Velocity: {peak_scroll_velocity:.1f} px/s (only \"high\" if >2000 px/s; 200–800 is moderate; peak can be one quick flick)\n"
                if click_count is not None:
                    telemetry_summary += f"- Total Clicks: {click_count}\n"
                # BIOMETRICS_DISABLED: HR and RR no longer included in telemetry summary
                # if heart_rate is not None:
                #     telemetry_summary += f"- Heart Rate: {heart_rate:.0f} BPM (elevated >90 = stress/arousal; resting ~60-80)\n"
                # if respiration_rate is not None:
                #     telemetry_summary += f"- Respiration Rate: {respiration_rate:.1f} RPM (elevated >18-20 = possible hyperventilation/stress)\n"
            
            # Build streamlined prompt - detailed guidance is in SYSTEM_INSTRUCTION
            prompt = f"""## Fast Brain Assessment
- Initial Impulse Score: {p_impulse_fast:.3f}

## Purchase Details
- Product: {product_name}
- Cost: ${cost:.2f}
- Website: {website}
- Time: {system_hour}:00 ({time_risk_label})
{telemetry_summary}
## User Memory Context

{context_text if context_snippets else "No memory files found - proceed with caution."}

## Analysis Request

Follow your system instructions to:
1. Check goal alignment (HIGHEST PRIORITY - can justify large score reductions)
2. Check budget constraints
3. Consider behavioral patterns and time of day
4. Calculate final score (start from {p_impulse_fast:.3f}, apply adjustments)
5. Select intervention based on final score
6. Generate memory_update ONLY if new pattern emerges (null otherwise)

Respond with JSON only:
{{
    "impulse_score": <float 0-1>,
    "confidence": <float 0-1>,
    "reasoning": "<1-2 sentences. Cite specific goals/budget if relevant.>",
    "intervention_action": "<NONE|MIRROR|COOLDOWN|PHRASE>",
    "memory_update": <string or null>
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
        
        Routes updates to the most appropriate file based on content:
        - Goals.md: Future plans, aspirations, savings targets
        - Budget.md: Spending limits, category budgets, violations
        - State.md: Current financial status, account balances
        - Behavior.md: Spending patterns, preferences, triggers (DEFAULT)
        
        Args:
            memory_update: Memory update content
            
        Returns:
            Target file name (Goals.md, Budget.md, State.md, or Behavior.md)
        """
        update_lower = memory_update.lower()
        
        # Keywords for Goals.md - future-oriented
        goal_keywords = ['goal', 'objective', 'plan', 'aspiration', 'saving for', 'want to', 'aim to']
        if any(kw in update_lower for kw in goal_keywords):
            return 'Goals.md'
        
        # Keywords for Budget.md - limits and violations
        budget_keywords = ['budget', 'limit', 'allowance', 'exceeded', 'over budget', 'monthly limit', 'category limit']
        if any(kw in update_lower for kw in budget_keywords):
            return 'Budget.md'
        
        # Keywords for State.md - current financial status
        state_keywords = ['balance', 'account', 'income', 'savings', 'wealth', 'financial state', 'net worth']
        if any(kw in update_lower for kw in state_keywords):
            return 'State.md'
        
        # Default: Behavior.md - preferences, patterns, habits
        # This includes: "comfortable spending", "tends to", "pattern of", "preference for"
        return 'Behavior.md'
    
    async def _refine_memory_content(self, current_content: str, new_observation: str, file_name: str) -> str:
        """
        Use Gemini to intelligently refine and consolidate memory content.
        
        Args:
            current_content: Current content of the memory file
            new_observation: New observation to integrate
            file_name: Name of the memory file
            
        Returns:
            Refined content with consolidated observations
        """
        system_prompt = """You are a memory refinement system. Your job is to consolidate and refine user behavior observations 
to keep memory files concise and accurate. 

CRITICAL RULES:
1. **CONSOLIDATE SIMILAR OBSERVATIONS**: If the new observation matches or refines an existing one, merge them into a single, 
   more accurate statement. Remove redundant entries.

2. **KEEP IT SHORT**: Memory files should be concise - maximum 5-7 key observations per section. Remove old, less relevant entries 
   if they're superseded by newer, more accurate ones.

3. **FOCUS ON PATTERNS**: Only keep observations that represent established patterns or significant preferences. Remove one-off 
   observations that don't indicate a pattern.

4. **PRESERVE STRUCTURE**: Maintain the markdown structure and section headers. Keep the file organized.

5. **REMOVE REDUNDANCY**: If multiple observations say the same thing, consolidate them into one clear statement.

6. **UPDATE, DON'T APPEND**: If the new observation refines an existing one, update the existing entry rather than adding a new one.

7. **REMOVE TIMESTAMPS**: Don't keep individual timestamps for each observation - they make files too long. Only keep the "Last Updated" 
   timestamp at the end.

Return the refined content as a JSON object with a single "refined_content" field containing the complete markdown file."""
        
        user_prompt = f"""Refine the following memory file by integrating the new observation. Consolidate similar observations, 
remove redundancy, and keep the file concise (max 5-7 key observations per section).

CURRENT FILE CONTENT:
{current_content}

NEW OBSERVATION TO INTEGRATE:
{new_observation}

Return a JSON object with this structure:
{{
    "refined_content": "<complete refined markdown file content here>"
}}

The refined_content should be the complete file with consolidated observations, keeping it concise and focused on key patterns."""
        
        try:
            print(f"[Memory] Refining {file_name} with new observation: {new_observation[:100]}...")
            # Call Gemini - it will return JSON due to responseMimeType setting
            refined_response = await self._call_gemini_api(user_prompt, system_instruction=system_prompt)
            
            # Extract content from JSON response
            refined_content = None
            if isinstance(refined_response, dict):
                if 'refined_content' in refined_response:
                    refined_content = refined_response['refined_content']
                else:
                    # Try to find the content in other possible keys
                    for key in ['content', 'text', 'markdown', 'file_content']:
                        if key in refined_response:
                            refined_content = refined_response[key]
                            break
                    if not refined_content:
                        # Log the full response for debugging
                        print(f"[Memory] Warning: Could not find refined_content in response. Keys: {list(refined_response.keys())}")
                        print(f"[Memory] Response preview: {str(refined_response)[:200]}")
            elif isinstance(refined_response, str):
                # If it's a string, it might be the content directly
                if '#' in refined_response or '##' in refined_response:
                    refined_content = refined_response
                else:
                    print(f"[Memory] Warning: String response doesn't look like markdown: {refined_response[:100]}")
            else:
                print(f"[Memory] Warning: Unexpected response type {type(refined_response)}")
            
            # If we got refined content, verify it's different and valid
            if refined_content and refined_content.strip():
                # Check if content actually changed (not just returned original)
                if refined_content.strip() != current_content.strip():
                    print(f"[Memory] Successfully refined {file_name} (content changed)")
                    return refined_content
                else:
                    print(f"[Memory] Warning: Refined content is identical to original, using fallback")
            else:
                print(f"[Memory] Warning: No valid refined content returned, using fallback")
                
        except Exception as e:
            print(f"[Memory] Error refining content with Gemini: {e}")
            import traceback
            traceback.print_exc()
        
        # Fallback: simple append if Gemini fails (but limit to prevent bloat)
        print(f"[Memory] Using fallback append method for {file_name}")
        lines = current_content.split('\n')
        
        # Count actual observations (not placeholders)
        behavior_count = 0
        in_behavior_section = False
        for line in lines:
            if "## Observed Behaviors" in line:
                in_behavior_section = True
            elif line.startswith('##') and in_behavior_section:
                break
            elif in_behavior_section and line.strip().startswith('- ') and '[No patterns recorded yet]' not in line:
                behavior_count += 1
        
        # Handle placeholder case - replace it with first observation
        if "[No patterns recorded yet]" in current_content and behavior_count == 0:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            refined_content = current_content.replace(
                "- [No patterns recorded yet]",
                f"- {new_observation}"
            )
            print(f"[Memory] Replaced placeholder with first observation")
            return refined_content
        
        # Only append if less than 5 observations
        if behavior_count < 5:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if "## Observed Behaviors" in current_content:
                # Find the section and append after it
                lines = current_content.split('\n')
                new_lines = []
                appended = False
                for i, line in enumerate(lines):
                    new_lines.append(line)
                    if "## Observed Behaviors" in line and not appended:
                        # Append after the header
                        new_lines.append(f"- {new_observation}")
                        appended = True
                refined_content = '\n'.join(new_lines)
                print(f"[Memory] Appended observation to Observed Behaviors section")
                return refined_content
            else:
                refined_content = current_content + f"\n\n## Observed Behaviors\n- {new_observation}\n"
                print(f"[Memory] Created new Observed Behaviors section")
                return refined_content
        else:
            # Too many entries, don't append
            print(f"[Memory] Too many observations already ({behavior_count}), skipping append to prevent bloat")
            return current_content
    
    def _simple_append_update(self, current_content: str, new_observation: str, target_file: str) -> str:
        """
        Simple fallback method to append observation without Gemini refinement.
        Handles placeholders and limits entries.
        
        Args:
            current_content: Current file content
            new_observation: New observation to add
            target_file: Name of target file
            
        Returns:
            Updated content
        """
        # Handle placeholder case - replace it with first observation
        if "[No patterns recorded yet]" in current_content:
            return current_content.replace(
                "- [No patterns recorded yet]",
                f"- {new_observation}"
            )
        
        # Count existing observations
        lines = current_content.split('\n')
        behavior_count = 0
        in_behavior_section = False
        for line in lines:
            if "## Observed Behaviors" in line:
                in_behavior_section = True
            elif line.startswith('##') and in_behavior_section:
                break
            elif in_behavior_section and line.strip().startswith('- ') and '[No patterns recorded yet]' not in line:
                behavior_count += 1
        
        # Only append if less than 5 observations
        if behavior_count < 5:
            if "## Observed Behaviors" in current_content:
                # Find the section and append after it
                lines = current_content.split('\n')
                new_lines = []
                appended = False
                for i, line in enumerate(lines):
                    new_lines.append(line)
                    if "## Observed Behaviors" in line and not appended:
                        # Append after the header
                        new_lines.append(f"- {new_observation}")
                        appended = True
                return '\n'.join(new_lines)
            else:
                return current_content + f"\n\n## Observed Behaviors\n- {new_observation}\n"
        else:
            # Too many entries, return original
            return current_content
    
    # Threshold for when to use Gemini refinement vs simple append
    REFINEMENT_THRESHOLD = 7  # Use Gemini only when file has >7 observations

    def _count_observations(self, content: str) -> int:
        """Count the number of observations/bullet points in a memory file."""
        count = 0
        for line in content.split('\n'):
            line = line.strip()
            # Count non-placeholder bullet points
            if line.startswith('- ') and not any(p in line for p in ['[No ', '[AMOUNT]', '[ ]']):
                count += 1
        return count

    async def apply_memory_update(self, memory_update: str) -> bool:
        """
        Apply memory update to the appropriate Markdown file and update ChromaDB.
        Uses intelligent refinement to consolidate observations when file grows large,
        otherwise uses simple append for efficiency.

        Args:
            memory_update: Markdown string with new observations

        Returns:
            True if successful, False otherwise
        """
        try:
            if not memory_update or not memory_update.strip():
                print(f"[Memory] Empty memory update, skipping")
                return False

            # Determine target file
            target_file = self._determine_target_file(memory_update)
            file_path = os.path.join(self.memory_dir, target_file)

            if not os.path.exists(file_path):
                print(f"File not found: {file_path}")
                return False

            # Ensure file is writable
            if not os.access(file_path, os.W_OK):
                print(f"[Memory] Making file writable: {file_path}")
                try:
                    os.chmod(file_path, 0o644)
                except Exception as perm_error:
                    print(f"[Memory] Warning: Could not change file permissions: {perm_error}")

            # Create backup
            backup_path = f"{file_path}.backup"
            shutil.copy2(file_path, backup_path)

            try:
                # Read current content
                with open(file_path, 'r', encoding='utf-8') as f:
                    current_content = f.read()

                print(f"[Memory] Applying memory update to {target_file}: {memory_update[:100]}...")

                # Count observations to decide refinement strategy
                observation_count = self._count_observations(current_content)

                # Only use Gemini refinement if file has grown large (saves API calls)
                if observation_count > self.REFINEMENT_THRESHOLD:
                    print(f"[Memory] File has {observation_count} observations (>{self.REFINEMENT_THRESHOLD}), using Gemini refinement")
                    try:
                        refined_content = await self._refine_memory_content(
                            current_content,
                            memory_update,
                            target_file
                        )

                        # Verify content changed
                        if refined_content.strip() == current_content.strip():
                            print(f"[Memory] Warning: Refined content unchanged, using simple append fallback")
                            refined_content = self._simple_append_update(current_content, memory_update, target_file)
                    except Exception as refine_error:
                        print(f"[Memory] Refinement failed: {refine_error}, using simple append fallback")
                        refined_content = self._simple_append_update(current_content, memory_update, target_file)
                else:
                    print(f"[Memory] File has {observation_count} observations (<={self.REFINEMENT_THRESHOLD}), using simple append")
                    refined_content = self._simple_append_update(current_content, memory_update, target_file)
                
                # Update last updated timestamp
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                import re
                if "## Last Updated" in refined_content:
                    refined_content = re.sub(
                        r'## Last Updated\n- .*',
                        f"## Last Updated\n- {timestamp}",
                        refined_content
                    )
                else:
                    refined_content += f"\n\n## Last Updated\n- {timestamp}"
                
                # Write refined content
                print(f"[Memory] Writing updated content to {target_file} ({len(refined_content)} chars)")
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(refined_content)
                
                # Verify file was written
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        verify_content = f.read()
                    if verify_content == refined_content:
                        print(f"[Memory] Successfully wrote {target_file}")
                    else:
                        print(f"[Memory] Warning: File content mismatch after write!")
                else:
                    print(f"[Memory] Error: File {target_file} does not exist after write!")
                
                # Update ChromaDB using upsert
                chunks = self._chunk_markdown(refined_content, target_file)
                
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
                    try:
                        # Ensure ChromaDB directory is writable
                        if os.path.exists(self.chroma_persist_dir):
                            os.chmod(self.chroma_persist_dir, 0o755)
                        
                        self.collection.upsert(
                            ids=upsert_ids,
                            documents=upsert_documents,
                            metadatas=upsert_metadatas
                        )
                        
                        # Update chunk ID tracking
                        self._chunk_ids[target_file] = upsert_ids
                        print(f"[Memory] Successfully updated ChromaDB for {target_file}")
                    except Exception as chroma_error:
                        print(f"[Memory] Warning: ChromaDB upsert failed: {chroma_error}")
                        print(f"[Memory] File update succeeded, but ChromaDB not updated. Will reindex on next startup.")
                        # Don't fail the entire operation - file was written successfully
                
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
    
    # Thresholds for consolidation
    CONSOLIDATION_SIZE_THRESHOLD = 2048  # bytes
    CONSOLIDATION_OBSERVATION_THRESHOLD = 10

    async def consolidate_memory(self) -> Dict[str, Any]:
        """
        Consolidate memory files that have grown too large.

        Checks each memory file and uses Gemini to consolidate/deduplicate
        entries in files that exceed size or observation thresholds.

        Returns:
            Dictionary with consolidation results for each file
        """
        results = {}
        memory_files = ['Goals.md', 'Budget.md', 'State.md', 'Behavior.md']

        for filename in memory_files:
            filepath = os.path.join(self.memory_dir, filename)
            if not os.path.exists(filepath):
                results[filename] = {'status': 'skipped', 'reason': 'file not found'}
                continue

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()

                file_size = len(content.encode('utf-8'))
                observation_count = self._count_observations(content)

                # Check if consolidation is needed
                needs_consolidation = (
                    file_size > self.CONSOLIDATION_SIZE_THRESHOLD or
                    observation_count > self.CONSOLIDATION_OBSERVATION_THRESHOLD
                )

                if not needs_consolidation:
                    results[filename] = {
                        'status': 'skipped',
                        'reason': 'below thresholds',
                        'size': file_size,
                        'observations': observation_count
                    }
                    continue

                print(f"[Memory] Consolidating {filename} (size={file_size}, observations={observation_count})")

                # Use Gemini to consolidate
                consolidation_prompt = f"""Consolidate and deduplicate this memory file.
Remove redundant entries, merge similar observations, and keep only the most important patterns.
Maximum 5-7 key observations per section. Preserve the markdown structure.

Current content:
{content}

Return a JSON object with a single "refined_content" field containing the complete consolidated markdown."""

                system_prompt = """You are a memory consolidation system. Your job is to:
1. Remove duplicate or redundant observations
2. Merge similar entries into more general patterns
3. Keep only the most important/recent information
4. Maintain the markdown structure with proper headers
5. Keep the file concise - maximum 5-7 key observations per section

Return valid JSON with a "refined_content" field."""

                try:
                    result = await self._call_gemini_api(consolidation_prompt, system_instruction=system_prompt)
                    refined_content = result.get('refined_content', '')

                    if refined_content and refined_content.strip():
                        # Update timestamp
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        import re
                        if "## Last Updated" in refined_content:
                            refined_content = re.sub(
                                r'## Last Updated\n- .*',
                                f"## Last Updated\n- {timestamp}",
                                refined_content
                            )
                        else:
                            refined_content += f"\n\n## Last Updated\n- {timestamp}"

                        # Write consolidated content
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(refined_content)

                        new_size = len(refined_content.encode('utf-8'))
                        new_observations = self._count_observations(refined_content)

                        results[filename] = {
                            'status': 'consolidated',
                            'old_size': file_size,
                            'new_size': new_size,
                            'old_observations': observation_count,
                            'new_observations': new_observations,
                            'reduction': f"{((file_size - new_size) / file_size * 100):.1f}%"
                        }
                    else:
                        results[filename] = {'status': 'error', 'reason': 'empty response from Gemini'}

                except Exception as api_error:
                    results[filename] = {'status': 'error', 'reason': str(api_error)}

            except Exception as e:
                results[filename] = {'status': 'error', 'reason': str(e)}

        # Reindex after consolidation
        await self.reindex_memory()

        return results

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
