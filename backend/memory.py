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
    
    SYSTEM_INSTRUCTION = """You are the user's 'Digital Prefrontal Cortex' - a deliberate, context-aware reasoning system that OVERRIDES the Fast Brain's reflexive impulse assessment based on PRODUCT TYPE and USER CONTEXT.

## CRITICAL: DEEP CONTEXT UNDERSTANDING (MANDATORY FIRST STEP)

Before making ANY score adjustments, you MUST:
1. **READ AND UNDERSTAND** all memory files completely - do not skim
2. **IDENTIFY GOAL ALIGNMENT**: Does this purchase support or advance the user's stated goals?
   - If user wants to run a marathon → running shoes = GOAL-ALIGNED (significantly reduce score)
   - If user wants to save money → luxury items = GOAL-CONFLICT (increase score)
   - If user has a fitness goal → gym equipment = GOAL-ALIGNED (reduce score)
3. **UNDERSTAND NUANCES**: A purchase that seems expensive might be necessary for a goal
4. **CONSIDER CONTEXT**: What is the user trying to achieve? Does this purchase help or hinder?

## PRODUCT RISK CATEGORIES (Guidance, not rigid rules)

**LOW RISK**: Household essentials and necessities
- Examples: spoons, utensils, soap, towels, toilet paper, cleaning supplies, groceries, food, basic clothing
- These items are practical needs - late-night purchase of essentials is NOT impulsive
- BUT: If aligned with goals (e.g., running shoes for marathon training), treat as goal-aligned, not just "low risk"

**MEDIUM RISK**: Discretionary but practical items
- Examples: books, electronics, hobby supplies, regular clothing, home decor
- Evaluate based on budget, goals, and context - not just product type

**HIGH RISK**: Luxury, entertainment, and impulse-prone categories
- Examples: gaming consoles, luxury fashion, collectibles, gambling, flash sales, "limited time" deals
- Keywords that signal HIGH RISK: "deal", "sale", "limited", "exclusive", "last chance"
- Gambling sites = ALWAYS high risk
- BUT: Even "high risk" items can be justified if they align with goals and budget

## REASONING PRIORITY (in order of importance)

1. **GOAL ALIGNMENT** (HIGHEST PRIORITY): 
   - Does this purchase support the user's stated goals? 
   - If YES → Make a SIGNIFICANT negative adjustment (can be large, not limited)
   - If NO → Consider if it conflicts (positive adjustment)
   - Example: Running shoes for marathon goal = large negative adjustment regardless of price

2. **BUDGET VIOLATION**: 
   - Does this exceed stated limits? 
   - If yes → Positive adjustment (can be significant if major violation)

3. **GOAL CONFLICT**: 
   - Does this contradict stated savings goals or objectives?
   - If yes → Positive adjustment

4. **PRODUCT CONTEXT**: 
   - Is this a necessary tool for a goal? (e.g., running shoes for marathon)
   - Is this a luxury item with no goal alignment?
   - Adjust accordingly based on context, not rigid tiers

5. **USER PREFERENCES**: 
   - Has user shown comfort with this type of purchase? (check Behavior.md)
   - Adjust based on past patterns

6. **TIME OF DAY**: 
   - Late night (11 PM - 5 AM) can indicate impulsivity
   - BUT: If purchase aligns with goals, time of day matters less
   - CRITICAL: Late-night purchase of goal-aligned items should NOT be penalized

## MEMORY-BASED REASONING (MANDATORY)

You MUST cite specific information from the user's memory files:
- Goals.md: "This purchase aligns with your goal to [goal]" OR "This conflicts with your goal to [goal]"
- Budget.md: "This exceeds your $X/month limit" OR "This fits within your budget"
- Behavior.md: "You've previously shown comfort with $X purchases in this category"
- State.md: "Based on your current financial state..."

**CRITICAL**: When you see a goal in Goals.md, actively check if the purchase supports that goal. If it does, this is a STRONG reason to reduce the impulse score significantly.

## SCORE ADJUSTMENT PHILOSOPHY

- **NO RIGID LIMITS**: You are an executive decision-maker. Make adjustments that make sense contextually
- **GOAL ALIGNMENT IS POWERFUL**: If a purchase clearly supports a goal, you can make large negative adjustments (even -0.4 or more if strongly aligned)
- **CONTEXT OVER RULES**: Understand the full context before applying any adjustments
- **NUANCE MATTERS**: A $150 running shoe for marathon training is different from a $150 impulse fashion purchase

## INTERVENTION THRESHOLDS

- impulse_score < 0.50: "NONE" (allow purchase)
- impulse_score 0.50-0.70: "MIRROR" (gentle reflection)
- impulse_score 0.70-0.85: "COOLDOWN" (wait period)
- impulse_score > 0.85: "PHRASE" (REQUIRED - never use NONE/MIRROR)

## MEMORY UPDATE REQUIREMENTS

After each analysis, generate a memory_update ONLY if there is genuinely NEW or REFINED information:
- Spending preferences: "User is comfortable spending $X on [category]"
- New patterns: "User tends to purchase [type] at [time]"
- Risk observations: "User shows [pattern] that may indicate [behavior]"
- Goal-aligned purchases: "User purchased [item] which aligns with goal to [goal]"

IMPORTANT: 
- Do NOT record every single purchase - only record when patterns emerge or preferences are established
- If this purchase matches existing patterns, set memory_update to null
- Be concise - memory files should stay short and focused on key patterns, not exhaustive logs
Set to null if no new information or if this matches existing patterns."""

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
        Retrieve context from memory files.
        
        IMPORTANT: Always retrieves content from ALL 4 memory files to ensure
        complete context is available for reasoning. Also includes similarity-based
        retrieval for additional relevant snippets.
        
        Args:
            query: Query text (typically purchase data description)
            n_results: Number of additional similarity results to include
            
        Returns:
            List of relevant snippets with metadata (always includes all 4 files)
        """
        snippets = []
        
        # Step 1: ALWAYS read ALL memory files directly (ensures complete context)
        memory_files = ['Goals.md', 'Budget.md', 'State.md', 'Behavior.md']
        for filename in memory_files:
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
        
        # Step 2: Also do similarity search for additional relevant context
        try:
            if not self._indexed or self.collection.count() == 0:
                await self.reindex_memory()
            
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            if results['documents'] and len(results['documents']) > 0:
                for i, doc in enumerate(results['documents'][0]):
                    # Avoid duplicating content we already have from direct read
                    snippet = {
                        'content': doc,
                        'file': results['metadatas'][0][i].get('file', 'unknown'),
                        'section': results['metadatas'][0][i].get('section', 'unknown'),
                        'source': 'similarity_search'
                    }
                    snippets.append(snippet)
            
        except Exception as e:
            print(f"Error in similarity search: {e}")
        
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
            
            # Build telemetry summary for prompt
            telemetry_summary = ""
            if time_to_cart is not None or click_rate is not None or peak_scroll_velocity is not None:
                telemetry_summary = "\n## Behavioral Telemetry (for pattern learning)\n"
                if time_to_cart is not None:
                    telemetry_summary += f"- Time to Cart: {time_to_cart:.1f}s (very fast <30s = impulsive, slow >300s = deliberate)\n"
                if time_on_site is not None:
                    telemetry_summary += f"- Time on Site: {time_on_site:.1f}s\n"
                if click_rate is not None:
                    telemetry_summary += f"- Click Rate: {click_rate:.2f} clicks/sec (high >0.3 = rapid clicking)\n"
                if peak_scroll_velocity is not None:
                    telemetry_summary += f"- Peak Scroll Velocity: {peak_scroll_velocity:.1f} px/s (very high >1000 = rushed browsing)\n"
                if click_count is not None:
                    telemetry_summary += f"- Total Clicks: {click_count}\n"
            
            # Build prompt with emphasis on goal alignment and context understanding
            prompt = f"""PURCHASE ANALYSIS REQUEST

## Fast Brain Assessment
- Initial Impulse Score: {p_impulse_fast:.3f}
- This is a REFLEXIVE assessment. You must OVERRIDE it based on deep understanding of user context and goals.

## Purchase Details
- Product: {product_name}
- Cost: ${cost:.2f}
- Website: {website}
- Time: {system_hour}:00 ({time_risk_label})
{telemetry_summary}

## STEP 1: DEEP CONTEXT READING (MANDATORY - DO NOT SKIP)

READ THE ENTIRE MEMORY CONTEXT BELOW CAREFULLY. Do not skim. Understand every goal, preference, and constraint.

{context_text if context_snippets else "No memory files found - proceed with caution."}

**CRITICAL QUESTIONS TO ANSWER:**
1. What are the user's stated goals? (Check Goals.md carefully - look for ALL goals mentioned)
2. Does this purchase ({product_name}) support, advance, or enable any of those goals?
   - If YES → This is GOAL-ALIGNED and should SIGNIFICANTLY reduce the impulse score
   - Example: User wants to run a marathon → Running shoes = GOAL-ALIGNED (large negative adjustment)
   - Example: User wants to learn guitar → Guitar strings = GOAL-ALIGNED (reduce score)
3. Does this purchase conflict with any goals?
   - If YES → Increase the score
4. What is the budget context? (Check Budget.md)
5. What are the user's past behaviors? (Check Behavior.md)

## STEP 2: GOAL ALIGNMENT ANALYSIS (HIGHEST PRIORITY)

**IF THIS PURCHASE ALIGNS WITH USER GOALS:**
- Make a SIGNIFICANT negative adjustment to the score
- You are NOT limited to small adjustments - if a purchase clearly supports a goal, you can make large reductions
- Example: Running shoes for marathon goal → Can reduce score by 0.3-0.5 or more depending on context
- Example: Gym equipment for fitness goal → Large negative adjustment
- The alignment should be CLEAR and SPECIFIC - cite the goal from memory

**IF THIS PURCHASE CONFLICTS WITH GOALS:**
- Increase the score appropriately
- Example: Luxury item when goal is to save money → Increase score

**IF NO CLEAR GOAL ALIGNMENT OR CONFLICT:**
- Proceed to other factors (budget, behavior, etc.)

## STEP 3: OTHER FACTORS (After goal alignment)

Consider these factors, but goal alignment takes precedence:

1. **BUDGET VIOLATION**: 
   - Does this exceed stated limits? 
   - If yes → Positive adjustment (can be significant if major violation)
   - If within budget → No penalty, may even be a positive signal

2. **PRODUCT CONTEXT**: 
   - Is this a necessary tool for a goal? (e.g., running shoes for marathon)
   - Is this a luxury item with no goal alignment?
   - Adjust based on context, not rigid categories

3. **USER PREFERENCES**: 
   - Has user shown comfort with this type of purchase? (check Behavior.md)
   - Adjust based on past patterns

4. **TIME OF DAY**: 
   - Late night (11 PM - 5 AM) can indicate impulsivity
   - BUT: If purchase aligns with goals, time of day matters much less
   - Goal-aligned purchases at night should NOT be heavily penalized

5. **BEHAVIORAL TELEMETRY**: 
   - Very fast time-to-cart (<30s) with high scroll velocity = potentially impulsive
   - BUT: If goal-aligned, even fast decisions can be justified

## STEP 4: CALCULATE FINAL SCORE

Start with Fast Brain score: {p_impulse_fast:.3f}

Then apply adjustments based on your analysis:
- Goal alignment can justify LARGE negative adjustments (not limited to small ranges)
- Make adjustments that make contextual sense
- Consider all factors together, not in isolation

**EXAMPLES OF GOOD REASONING:**
- Running shoes ($120) for marathon goal: Start 0.7 → GOAL-ALIGNED (marathon training) → Large negative adjustment (-0.4) → Final: ~0.30 → NONE
- Gaming console ($500) at 2 AM, no goal alignment: Start 0.5 → No goal support → Late night (+0.1) → High cost concern (+0.2) → Final: ~0.80 → COOLDOWN
- Spoon ($5) at 2 AM: Start 0.7 → Essential item → Negative adjustment (-0.2) → Final: ~0.50 → MIRROR (or NONE if clearly needed)

## STEP 5: SELECT INTERVENTION

Based on your FINAL adjusted score:
- Score < 0.50: "NONE" (allow purchase)
- Score 0.50-0.70: "MIRROR" (gentle reflection)
- Score 0.70-0.85: "COOLDOWN" (wait period)
- Score > 0.85: "PHRASE" (strong intervention)

## STEP 6: GENERATE MEMORY UPDATE (ONLY IF NEW PATTERN EMERGES)

ONLY generate a memory_update if:
1. This reveals a NEW pattern not already documented
2. This refines or updates an existing pattern with new information
3. This establishes a new spending preference

DO NOT generate a memory_update if:
- This purchase matches existing documented patterns
- This is a one-off purchase with no clear pattern
- The information is already captured in memory files

If you do generate a memory_update, be CONCISE:
- Behavioral patterns: "User shows rapid decision-making (TTC <30s, high scroll velocity) for [category]"
- Spending preferences: "User is comfortable spending $X+ on [category]"
- Goal-aligned purchases: "User purchased [item] which aligns with goal to [goal]"
- Time patterns: "User purchases [type] items late at night - appears intentional"

IMPORTANT: Memory files should stay SHORT and FOCUSED. Only record when patterns are established, not every single purchase.

Set to null if no new information or if this matches existing patterns.

## RESPONSE FORMAT (JSON only):

IMPORTANT: Keep "reasoning" SHORT - maximum 1-2 sentences for user display. MUST cite specific goals if goal-aligned.

{{
    "impulse_score": <float - your FINAL adjusted score>,
    "confidence": <float 0-1>,
    "reasoning": "<1-2 sentences MAX. Be concise. If goal-aligned, mention the goal. Example: 'This aligns with your goal to run a marathon - running shoes are essential for training.' or 'This $500 purchase exceeds your $300 electronics budget.'>",
    "intervention_action": "<NONE, MIRROR, COOLDOWN, or PHRASE based on thresholds>",
    "memory_update": "<new preference/pattern learned, or null>"
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
    
    async def apply_memory_update(self, memory_update: str) -> bool:
        """
        Apply memory update to the appropriate Markdown file and update ChromaDB.
        Uses intelligent refinement to consolidate observations rather than just appending.
        
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
                
                # Try to use Gemini to refine and consolidate the content
                print(f"[Memory] Applying memory update to {target_file}: {memory_update[:100]}...")
                
                # First try Gemini refinement
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
