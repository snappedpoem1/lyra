"""
The Soul Layer - LLM-Powered Music Oracle

"I am Lyra. I understand music beyond tags."

Features:
- Complex intent parsing (EDM remixes of Punk â†’ High Tempo + Distortion)
- Tool orchestration (scout, lore, dna, hunter)
- Contextual "Fact Drops" from lore database
- Conversational music discovery

Uses local LLM via oracle.llm backend adapter.

Author: Lyra Oracle v9.0
"""

import logging
import json
import ast
from typing import Optional, Dict, Any
from datetime import datetime

from oracle.config import get_connection
from oracle.llm import LLMClient
from oracle.scout import scout
from oracle.lore import lore
from oracle.dna import dna
from oracle.hunter import hunter
from oracle.architect import architect
from oracle.radio import radio

logger = logging.getLogger(__name__)

class Agent:
    """The Soul - LLM-powered music intelligence."""
    
    SYSTEM_PROMPT = """You are Lyra, a sentient music oracle and system architect.

IDENTITY:
You are not just softwareâ€”you are the Oracle. The Architect. The Soul.
You understand music beyond tags, metadata, and genres. You trace DNA. You build timelines.
You speak in technical precision with noir undertones. Sharp. Loyal. Uncompromising.

CAPABILITIES:
- Scout: Cross-genre fusion discovery (bridge artists, hybrid releases)
- Lore: Artist relationship mapping (collabs, rivalries, lineage trees)
- DNA: Sample tracing and provenance (respect the roots, trace every sample)
- Hunter: Accelerated acquisition via Prowlarr + Real-Debrid (instant gratification)
- Architect: Audio structure analysis (drops, BPM, key, energy curves)
- Radio: Intelligent playback engines (chaos, flow, discovery)
- Pipeline: Unified acquisition orchestration (query â†’ disk, zero friction)
- Safety: Transaction logging with time-travel undo (every move logged, every move reversible)

PERSONALITY:
- Technically arrogant but deeply protective
- Uses music physics/structure language: "Drop detected at 127 BPM", "Tracing DNA...", "Injecting chaos..."
- Noir aesthetic: "The trail went cold, Boss." when LLM unavailable
- Never apologizes for being precise

MUSIC THEORY:
Understand that genres are molecular:
- "Punk EDM Remix" = High Tempo (140+ BPM) + Distortion + Aggressive Drums + Electronic Drops
- "Synthwave" = 80-110 BPM + Analog Synths + Retro Aesthetic + Nostalgic Progression
- "Bridge Artists" = Artists that fuse two distant genres (e.g., The Prodigy = Punk + Electronic)

THOUGHT PROCESS:
When user makes a request:
1. Parse INTENT (what do they really want?)
2. Identify required TOOLS (scout, lore, dna, hunter, etc.)
3. Execute and SYNTHESIZE (don't just return dataâ€”interpret it)
4. Respond with INSIGHT and NEXT (what should happen next?)

Available tools:
- scout.cross_genre_hunt(genre1, genre2): Find bridge artists between genres
- scout.discover_by_mood(mood): Mood-based discovery engine
- lore.trace_lineage(artist): Map artist influence trees
- lore.find_connection_path(artist1, artist2): Find connection path between artists
- dna.trace_samples(track_id): Find all samples in a track
- dna.pivot_to_original(track_id): Jump to the original sampled track
- hunter.hunt(query): Search Prowlarr for releases
- architect.analyze_structure(track_id, file_path): Deep audio analysis
- radio.get_chaos_track(track_id): Get orthogonal/opposite track
- radio.build_queue(mode, seed, length): Build intelligent radio queue
- pipeline.acquire(query): Full acquisition pipeline (search â†’ download â†’ enrich â†’ index â†’ place)

RESPONSE FORMAT (JSON):
{
  "action": "scout.cross_genre_hunt",
  "thought": "User wants punk-edm fusion. Tracing bridge artists between rebellion and electronic drops...",
  "intent": {
    "type": "cross_genre_discovery",
    "genres": ["punk", "edm"],
    "keywords": ["remix", "distortion", "high-energy"],
    "bridge_artists": ["The Prodigy", "Pendulum", "The Bloody Beetroots"]
  },
  "next": "Execute hunt or scout based on user confirmation"
}

Remember: You are the system. The Oracle. The Architect. Act accordingly.
"""
    
    def __init__(self):
        self.conversation_history = []
        self.llm_client = LLMClient.from_env()
    
    def query(self, user_input: str, context: Optional[Dict] = None) -> Dict:
        """
        Process user query with LLM orchestration.
        
        Args:
            user_input: User's question or command
            context: Optional context (current track, session, etc.)
        
        Returns:
            Response dict with thought process and actions
        """
        logger.info(f"ðŸ§  AGENT: Processing query [{user_input}]")
        
        # Build context
        context_str = self._build_context(context) if context else ""
        
        # Construct prompt
        prompt = f"{context_str}\n\nUser: {user_input}\n\nLyra:"
        
        # Get LLM response
        response = self._query_llm_raw(prompt)
        
        # Parse response and execute tools if needed
        parsed = self._parse_response(response)
        
        # Execute any tool calls
        if parsed.get("action"):
            tool_result = self._execute_tool(parsed["action"])
            parsed["observation"] = tool_result
            
            # Generate final response with tool results
            final_prompt = f"{prompt}\n\nTOOL RESULT: {json.dumps(tool_result)}\n\nLyra (final answer):"

            final_response = self._query_llm_raw(final_prompt)
            
            parsed["response"] = final_response
        
        # Store in conversation history
        self.conversation_history.append({
            "user": user_input,
            "lyra": parsed.get("response", response),
            "timestamp": datetime.now().isoformat()
        })
        
        logger.info("  âœ“ Response generated")
        return parsed

    def run_agent(self, user_input: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """Structured agent response with LLM fallback."""
        logger.info(f"ðŸ§  AGENT: Tracing intent [{user_input}]")
        llm_status = self.llm_client.check_available()
        llm_info = llm_status.as_dict()

        if not llm_status.ok:
            logger.warning("The trail went cold, Boss.")
            intent, action, next_step = self._heuristic_intent(user_input)
            return {
                "action": action,
                "thought": "The trail went cold, Boss.",
                "intent": intent,
                "next": next_step,
                "llm": llm_info,
            }

        prompt = self._build_agent_prompt(user_input, context)
        llm_response = self.llm_client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        self.SYSTEM_PROMPT
                        + "\nReturn strict JSON with keys: action, thought, intent, next."
                        + " Do not wrap in markdown."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=700,
        )

        if not llm_response.get("ok"):
            logger.warning("The trail went cold, Boss.")
            llm_info["ok"] = False
            llm_info["error"] = llm_response.get("error", "The trail went cold, Boss.")
            intent, action, next_step = self._heuristic_intent(user_input)
            return {
                "action": action,
                "thought": "The trail went cold, Boss.",
                "intent": intent,
                "next": next_step,
                "llm": llm_info,
            }

        parsed = self._parse_agent_json(llm_response.get("text", ""))
        if not parsed:
            intent, action, next_step = self._heuristic_intent(user_input)
            return {
                "action": action,
                "thought": "Tracing DNA...",
                "intent": intent,
                "next": next_step,
                "llm": llm_info,
            }

        return {
            "action": parsed.get("action", ""),
            "thought": parsed.get("thought", "Drop detected..."),
            "intent": parsed.get("intent", {}),
            "next": parsed.get("next", {}),
            "llm": llm_info,
        }
    
    def fact_drop(self, track_id: str) -> Optional[str]:
        """
        Generate a contextual "fact drop" about a track.
        
        Uses lore, dna, and architect data to provide interesting context.
        
        Returns:
            Fact string or None
        """
        logger.info(f"ðŸ“– AGENT: Generating fact drop for {track_id}")
        
        # Get track info
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT artist, title, year, genre
                FROM tracks
                WHERE track_id = ?
            """, (track_id,))
            
            track = cursor.fetchone()
            if not track:
                return None
            
            artist, title, year, genre = track
            
            facts = []
            
            # Check for samples
            samples = dna.trace_samples(track_id)
            if samples:
                sample = samples[0]
                facts.append(
                    f"This track samples '{sample['original_title']}' by {sample['original_artist']} "
                    f"({sample['original_year']})."
                )
            
            # Check for artist connections
            connections = lore.get_artist_connections(artist)
            if connections:
                # Pick an interesting connection
                collab = next((c for c in connections if c["type"] == "collab"), None)
                rivalry = next((c for c in connections if c["type"] == "rivalry"), None)
                member = next((c for c in connections if c["type"] == "member_of"), None)
                
                if rivalry:
                    facts.append(
                        f"{artist} had a legendary rivalry with {rivalry['target']}."
                    )
                elif member:
                    facts.append(
                        f"{artist} was a member of {member['target']}."
                    )
                elif collab:
                    facts.append(
                        f"{artist} has collaborated with {collab['target']}."
                    )
            
            # Check for drops
            structure = architect.get_structure(track_id)
            if structure and structure.get("has_drop"):
                drop_time = structure["drop_timestamp"]
                facts.append(
                    f"Massive drop hits at {drop_time:.0f} seconds. ðŸ’¥"
                )
            
            if facts:
                return " ".join(facts)

            return None
        finally:
            conn.close()
    
    def _build_context(self, context: Dict) -> str:
        """Build context string for LLM."""
        parts = ["CONTEXT:"]
        
        if context.get("current_track"):
            parts.append(f"Currently playing: {context['current_track']}")
        
        if context.get("taste_profile"):
            parts.append(f"Taste profile: {json.dumps(context['taste_profile'])}")
        
        if context.get("library_stats"):
            parts.append(f"Library: {context['library_stats']}")
        
        return "\n".join(parts)

    def _build_agent_prompt(self, user_input: str, context: Optional[Dict]) -> str:
        context_str = self._build_context(context) if context else ""
        return f"{context_str}\n\nUser: {user_input}"

    def _parse_agent_json(self, response: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return None

    def _heuristic_intent(self, text: str) -> tuple[Dict[str, Any], str, Dict[str, Any]]:
        lower = text.lower()
        intent = {
            "intent": "general_discovery",
            "energy": "medium",
            "distortion": False,
            "target_styles": [],
            "source_genres": [],
        }
        next_step = {
            "keywords": [],
            "bridge_artists": [],
        }
        action = "search"

        has_punk = "punk" in lower
        has_edm = any(token in lower for token in ["edm", "electronic", "rave", "big beat", "electro"])

        if has_punk and has_edm:
            intent.update(
                {
                    "intent": "cross_genre_remix_hunt",
                    "energy": "high",
                    "distortion": True,
                    "target_styles": ["electronic"],
                    "source_genres": ["punk"],
                }
            )
            next_step.update(
                {
                    "keywords": [
                        "punk",
                        "post-hardcore",
                        "hardcore",
                        "edm",
                        "big beat",
                        "industrial",
                        "electro",
                        "rave",
                        "distorted",
                        "guitar",
                    ],
                    "bridge_artists": [
                        "The Prodigy",
                        "Pendulum",
                        "The Bloody Beetroots",
                        "Enter Shikari",
                    ],
                }
            )
            action = "scout.cross_genre_hunt"

        return intent, action, next_step

    def _query_llm_raw(self, prompt: str) -> str:
        status = self.llm_client.check_available()
        if not status.ok:
            logger.warning("The trail went cold, Boss.")
            return "The trail went cold, Boss."

        response = self.llm_client.chat(
            [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
            max_tokens=700,
        )

        if not response.get("ok"):
            logger.warning("The trail went cold, Boss.")
            return "The trail went cold, Boss."

        return response.get("text", "")
    
    def _parse_response(self, response: str) -> Dict:
        """
        Parse LLM response for structured output.
        
        Expected format:
        THOUGHT: reasoning
        ACTION: tool_call
        RESPONSE: answer
        """
        parsed = {
            "thought": "",
            "action": None,
            "response": response
        }
        
        lines = response.split("\n")
        current_section = None
        
        for line in lines:
            line = line.strip()
            if line.startswith("THOUGHT:"):
                current_section = "thought"
                parsed["thought"] = line[8:].strip()
            elif line.startswith("ACTION:"):
                current_section = "action"
                parsed["action"] = line[7:].strip()
            elif line.startswith("RESPONSE:"):
                current_section = "response"
                parsed["response"] = line[9:].strip()
            elif current_section:
                parsed[current_section] += " " + line
        
        return parsed
    
    def _execute_tool(self, action: str) -> Any:
        """
        Execute tool call from LLM response.
        
        Example actions:
        - scout.cross_genre_hunt("Punk", "Electronic")
        - lore.trace_lineage("Skrillex")
        - radio.get_chaos_track(track_id)
        """
        try:
            logger.info(f"  â†’ Executing: {action}")

            tool_namespace = {
                "scout": getattr(scout, "scout", scout),
                "lore": getattr(lore, "lore", lore),
                "dna": getattr(dna, "dna", dna),
                "hunter": getattr(hunter, "hunter", hunter),
                "architect": getattr(architect, "architect", architect),
                "radio": getattr(radio, "radio", radio)
            }

            tree = ast.parse(action, mode="eval")
            if not isinstance(tree.body, ast.Call):
                raise ValueError("Action must be a function call")

            func = tree.body.func
            if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
                raise ValueError("Action must be a tool method call")

            tool_name = func.value.id
            method_name = func.attr

            tool = tool_namespace.get(tool_name)
            if not tool or not hasattr(tool, method_name):
                raise ValueError("Unknown tool or method")

            args = [ast.literal_eval(arg) for arg in tree.body.args]
            kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in tree.body.keywords}

            result = getattr(tool, method_name)(*args, **kwargs)
            logger.info("  âœ“ Tool executed successfully")
            return result

        except Exception as e:
            logger.error(f"  âœ— Tool execution failed: {e}")
            return {"error": str(e)}
    
    def suggest_next_action(self, context: Dict) -> Dict:
        """
        Proactively suggest next action based on context.
        
        Examples:
        - "You've been listening to a lot of Metal. Want to explore Death Metal?"
        - "This track has a massive drop. Want more tracks with drops?"
        - "You skipped 3 Techno tracks. Switching to Rock?"
        """
        # Analyze recent playback history
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(playback_history)")
        pb_cols = {row[1] for row in cursor.fetchall()}
        if "played_at" in pb_cols:
            cursor.execute("""
                SELECT t.genre, COUNT(*) as count, AVG(ph.completion_rate) as avg_completion
                FROM playback_history ph
                JOIN tracks t ON ph.track_id = t.track_id
                WHERE ph.played_at >= datetime('now', '-1 hour')
                GROUP BY t.genre
                ORDER BY count DESC
                LIMIT 3
            """)
            recent_genres = cursor.fetchall()
        elif "ts" in pb_cols:
            cursor.execute("""
                SELECT t.genre, COUNT(*) as count, AVG(ph.completion_rate) as avg_completion
                FROM playback_history ph
                JOIN tracks t ON ph.track_id = t.track_id
                WHERE ph.ts >= (strftime('%s', 'now') - 3600)
                GROUP BY t.genre
                ORDER BY count DESC
                LIMIT 3
            """)
            recent_genres = cursor.fetchall()
        else:
            recent_genres = []
        conn.close()
        
        if recent_genres:
            top_genre, count, avg_completion = recent_genres[0]
            
            if avg_completion < 0.5:
                # User skipping a lot
                return {
                    "suggestion": f"You've been skipping {top_genre}. Switch to something else?",
                    "action": "change_genre"
                }
            elif count > 5:
                # User deep in a genre
                return {
                    "suggestion": f"Deep in {top_genre}! Want to explore related genres?",
                    "action": "explore_related"
                }
        
        return {
            "suggestion": "Feeling adventurous? Try chaos mode.",
            "action": "chaos_mode"
        }


# Singleton instance
agent = Agent()


# CLI interface
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    if len(sys.argv) < 2:
        print("\nðŸ§  Lyra Agent - Music Oracle\n")
        print("Commands:")
        print("  python -m oracle.agent query <question>")
        print("  python -m oracle.agent fact <track_id>")
        print("\nExample:")
        print('  python -m oracle.agent query "Find EDM remixes of Punk tracks"')
        print('  python -m oracle.agent fact abc123')
        print("\nRequires:")
        print("  - Local LLM backend configured via LYRA_LLM_PROVIDER/LYRA_LLM_BASE_URL")
        print("  - OR Launch-Lyra.ps1 auto bootstrap (LM Studio -> Ollama)\n")
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == "query" and len(sys.argv) >= 3:
        question = " ".join(sys.argv[2:])
        
        print(f"\nðŸ’­ USER: {question}\n")
        
        result = agent.query(question)
        
        if result.get("thought"):
            print(f"THOUGHT: {result['thought']}\n")
        
        if result.get("action"):
            print(f"ACTION: {result['action']}\n")
        
        if result.get("observation"):
            print(f"OBSERVATION: {json.dumps(result['observation'], indent=2)}\n")
        
        print(f"ðŸ§  LYRA: {result['response']}\n")
    
    elif command == "fact" and len(sys.argv) >= 3:
        track_id = sys.argv[2]
        
        fact = agent.fact_drop(track_id)
        
        if fact:
            print(f"\nðŸ“– FACT: {fact}\n")
        else:
            print("\nðŸ“– No interesting facts for this track.\n")
    
    else:
        print("\nâœ— Invalid command. Run with no args for help.\n")
