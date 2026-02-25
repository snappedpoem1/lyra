"""
The Operations Console - Unified CLI Interface

"One command to rule them all."

Commands:
- doctor: System diagnostics
- hunt: Trigger acquisition pipeline
- vibe: Create vibes from natural language
- undo: Safety rollback
- serve: Start Flask API
- agent: Query the LLM agent
- index: Manage embeddings
- scan: Library scanner

Author: Lyra Oracle v10.0
"""

import sys
import logging
from typing import Optional


logger = logging.getLogger(__name__)

# ASCII Art Banner
BANNER = r"""
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘                                                           â•‘
â•‘   â–ˆâ–ˆâ•—  â–ˆâ–ˆâ•—   â–ˆâ–ˆâ•—â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—                          â•‘
â•‘   â–ˆâ–ˆâ•‘  â•šâ–ˆâ–ˆâ•— â–ˆâ–ˆâ•”â•â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•—â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•—                         â•‘
â•‘   â–ˆâ–ˆâ•‘   â•šâ–ˆâ–ˆâ–ˆâ–ˆâ•”â• â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•”â•â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•‘                         â•‘
â•‘   â–ˆâ–ˆâ•‘    â•šâ–ˆâ–ˆâ•”â•  â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•—â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•‘                         â•‘
â•‘   â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—â–ˆâ–ˆâ•‘   â–ˆâ–ˆâ•‘  â–ˆâ–ˆâ•‘â–ˆâ–ˆâ•‘  â–ˆâ–ˆâ•‘                         â•‘
â•‘   â•šâ•â•â•â•â•â•â•â•šâ•â•   â•šâ•â•  â•šâ•â•â•šâ•â•  â•šâ•â•                         â•‘
â•‘                                                           â•‘
â•‘   The Oracle. The Architect. The Soul.                   â•‘
â•‘   Music Intelligence Platform v10.0                      â•‘
â•‘                                                           â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
"""


def print_banner():
    """Print the Lyra banner."""
    print(BANNER)


def cmd_doctor():
    """Run system diagnostics."""
    print("ðŸ” Running system diagnostics...\n")
    
    from oracle.doctor import run_doctor, _render
    
    checks = run_doctor()
    return _render(checks)


def cmd_hunt(query: str):
    """Trigger acquisition pipeline."""
    print(f"Hunting: {query}\n")

    from oracle import pipeline as pipeline_api

    print("WARNING: Deprecated console path; delegating to converged smart pipeline wrapper.")

    job_id = pipeline_api.start_acquisition(query)
    print(f"Job ID: {job_id}\n")

    try:
        result = pipeline_api.run_pipeline(job_id)
        state = (result or {}).get("state", "unknown")
        payload = (result or {}).get("result", {})
        print(f"Pipeline state: {state}")

        if payload.get("filepath"):
            print(f"Placed at: {payload['filepath']}")
        elif payload.get("rejection_reason"):
            print(f"Rejected: {payload['rejection_reason']}")

        return 0

    except Exception as e:
        print(f"âŒ Pipeline failed: {e}")
        return 1


def cmd_vibe_create(name: str, prompt: str):
    """Create a vibe from natural language."""
    print(f"ðŸŒŠ Creating vibe: {name}\n")
    print(f"Prompt: {prompt}\n")
    
    from oracle import vibes
    
    try:
        # Create vibe using existing save_vibe (uses prompt as query)
        vibe = vibes.save_vibe(name, prompt)
        print(f"âœ… Vibe created: {vibe['name']}")
        print(f"Query: {vibe.get('query', 'N/A')}")
        return 0
    
    except Exception as e:
        print(f"âŒ Vibe creation failed: {e}")
        return 1


def cmd_undo(n: int = 1):
    """Undo last N operations."""
    print(f"âª Rolling back {n} operation(s)...\n")
    
    from oracle.safety import undo_last
    
    try:
        undone = undo_last(n)
        print(f"âœ… Rolled back {len(undone)} operation(s)")
        
        for txn in undone:
            print(f"   Undone: {txn.action} {txn.source} â†’ {txn.target}")
        
        return 0
    
    except Exception as e:
        print(f"âŒ Undo failed: {e}")
        return 1


def cmd_serve(host: str = "0.0.0.0", port: int = 5000):
    """Start Flask API server."""
    print(f"ðŸš€ Starting API server on {host}:{port}...\n")
    
    try:
        # Import and run Flask app
        import lyra_api
        lyra_api.app.run(host=host, port=port, debug=False)
        return 0
    
    except Exception as e:
        print(f"âŒ Server failed: {e}")
        return 1


def cmd_agent(query: str):
    """Send query to LLM agent."""
    print(f"ðŸ§  Querying agent: {query}\n")
    
    from oracle.agent import agent
    
    try:
        result = agent.run_agent(query)
        
        print(f"ðŸ’­ Thought: {result.get('thought', 'N/A')}")
        print(f"ðŸŽ¯ Action: {result.get('action', 'N/A')}")
        print(f"ðŸ“‹ Intent: {result.get('intent', {})}")
        print(f"âž¡ï¸ Next: {result.get('next', 'N/A')}")
        print(f"ðŸ§  LLM: {result.get('llm', 'N/A')}")
        
        return 0
    
    except Exception as e:
        print(f"âŒ Agent query failed: {e}")
        return 1


def cmd_index(library_path: Optional[str] = None, force: bool = False):
    """Generate embeddings for library."""
    print("ðŸ§¬ Indexing library...\n")
    
    from oracle.indexer import index_library
    
    try:
        result = index_library(library_path=library_path, force_reindex=force)
        print(f"âœ… Indexed: {result.get('indexed', 0)} tracks")
        
        if result.get('failed', 0) > 0:
            print(f"âš ï¸ Failed: {result.get('failed', 0)} tracks")
        
        return 0
    
    except Exception as e:
        print(f"âŒ Indexing failed: {e}")
        return 1


def cmd_scan(paths: Optional[list] = None):
    """Scan library for metadata."""
    print("ðŸ“¡ Scanning library...\n")
    
    
    try:
        # Get library base if no paths specified
        if not paths:
            from oracle.config import LIBRARY_BASE
            paths = [str(LIBRARY_BASE)]
        
        for path in paths:
            print(f"Scanning: {path}")
            # TODO: Implement scan_library() in scanner.py
            # result = scan_library(path)
        
        print(f"âœ… Scan complete")
        return 0
    
    except Exception as e:
        print(f"âŒ Scan failed: {e}")
        return 1


def cmd_history(n: int = 10):
    """Show operation history from journal."""
    print(f"ðŸ“œ Last {n} operations:\n")
    
    from oracle.safety import get_journal
    
    journal = get_journal()
    transactions = journal.read_last(n)
    
    if not transactions:
        print("No operations in journal.")
        return 0
    
    for txn in transactions:
        status_icon = {"applied": "âœ…", "failed": "âŒ", "planned": "ðŸ“‹"}.get(txn.status, "âšª")
        print(f"{status_icon} [{txn.timestamp}] {txn.action}")
        print(f"   {txn.source} â†’ {txn.target}")
        
        if txn.error:
            print(f"   Error: {txn.error}")
        print()
    
    return 0


def cmd_help():
    """Show help message."""
    print_banner()
    print("Available commands:\n")
    
    commands = {
        "doctor": "Run system diagnostics (DB, LLM, ChromaDB, disk space)",
        "hunt <query>": "Search and acquire music via Prowlarr + Real-Debrid",
        "vibe create --name <name> --prompt <prompt>": "Generate vibe playlist from natural language",
        "undo [n]": "Rollback last N file operations (default: 1)",
        "serve [--host HOST] [--port PORT]": "Start Flask API server (default: 0.0.0.0:5000)",
        "agent <query>": "Query the LLM agent for music intelligence",
        "index [--path PATH] [--force]": "Generate CLAP embeddings for library",
        "scan [paths...]": "Scan library for metadata extraction",
        "history [n]": "Show last N operations from journal (default: 10)",
        "score (--all | --track <id>) [--limit N] [--rescore]": "Score tracks across emotional dimensions (writes require apply_allowed)",
        "help": "Show this help message"
    }
    
    for cmd, desc in commands.items():
        print(f"  {cmd:50s} - {desc}")
    
    print("\nExamples:")
    print("  lyra doctor")
    print("  lyra hunt 'Aphex Twin - Windowlicker'")
    print("  lyra vibe create --name 'Late Night Drive' --prompt 'Chill synthwave for midnight cruising'")
    print("  lyra agent 'find me some punk edm remixes'")
    print("  lyra score --all --limit 200")
    print("  lyra score --track <track_id>")
    print("  lyra undo 3")
    print("  lyra serve --port 8080")
    print()


def cmd_score(all_tracks: bool = False, track_id: Optional[str] = None, limit: int = 0, rescore: bool = False):
    """Score track(s) into `track_scores`."""
    from oracle.scorer import score_all, score_track

    if not all_tracks and not track_id:
        print("Usage: lyra score --all [--limit N] [--rescore] | lyra score --track <id> [--rescore]")
        return 1

    if all_tracks:
        stats = score_all(limit=limit, persist=True, force=rescore)
        print(f"âœ… Scoring complete: {stats}")
        return 0

    result = score_track(track_id or "", persist=True, force=rescore)
    print(f"âœ… Score: {result}")
    return 0


def parse_args(args: list) -> tuple:
    """
    Parse command-line arguments.
    
    Returns (command, kwargs)
    """
    if not args:
        return ("help", {})
    
    command = args[0]
    kwargs = {}
    positional = []
    
    i = 1
    while i < len(args):
        arg = args[i]
        
        if arg.startswith("--"):
            # Long option
            key = arg[2:]
            
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                value = args[i + 1]
                kwargs[key] = value
                i += 2
            else:
                kwargs[key] = True
                i += 1
        elif arg.startswith("-"):
            # Short option
            key = arg[1:]
            
            if i + 1 < len(args) and not args[i + 1].startswith("-"):
                value = args[i + 1]
                kwargs[key] = value
                i += 2
            else:
                kwargs[key] = True
                i += 1
        else:
            # Positional argument
            positional.append(arg)
            i += 1
    
    kwargs["_positional"] = positional
    return (command, kwargs)


def main():
    """Main entry point for Lyra Console."""
    command, kwargs = parse_args(sys.argv[1:])
    positional = kwargs.pop("_positional", [])
    
    # Route to command handlers
    try:
        if command == "doctor":
            return cmd_doctor()
        
        elif command == "hunt":
            if not positional:
                print("Usage: lyra hunt <query>")
                return 1
            query = " ".join(positional)
            return cmd_hunt(query)
        
        elif command == "vibe":
            if not positional or positional[0] != "create":
                print("Usage: lyra vibe create --name <name> --prompt <prompt>")
                return 1
            
            name = kwargs.get("name")
            prompt = kwargs.get("prompt")
            
            if not name or not prompt:
                print("Usage: lyra vibe create --name <name> --prompt <prompt>")
                return 1
            
            return cmd_vibe_create(name, prompt)
        
        elif command == "undo":
            n = int(kwargs.get("n", positional[0] if positional else 1))
            return cmd_undo(n)
        
        elif command == "serve":
            host = kwargs.get("host", "0.0.0.0")
            port = int(kwargs.get("port", 5000))
            return cmd_serve(host, port)
        
        elif command == "agent":
            if not positional:
                print("Usage: lyra agent <query>")
                return 1
            query = " ".join(positional)
            return cmd_agent(query)
        
        elif command == "index":
            library_path = kwargs.get("path")
            force = kwargs.get("force", False)
            return cmd_index(library_path, force)
        
        elif command == "scan":
            return cmd_scan(positional if positional else None)
        
        elif command == "history":
            n = int(kwargs.get("n", positional[0] if positional else 10))
            return cmd_history(n)

        elif command == "score":
            all_tracks = bool(kwargs.get("all", False))
            track_id = kwargs.get("track") or kwargs.get("track-id")
            limit = int(kwargs.get("limit", 0) or 0)
            rescore = bool(kwargs.get("rescore", False))
            return cmd_score(all_tracks=all_tracks, track_id=track_id, limit=limit, rescore=rescore)
        
        elif command == "help":
            cmd_help()
            return 0
        
        else:
            print(f"Unknown command: {command}")
            print("Run 'lyra help' for usage.")
            return 1
    
    except KeyboardInterrupt:
        print("\n\nâš¡ Interrupted by user.")
        return 130
    
    except Exception as e:
        print(f"\nâŒ Fatal error: {e}")
        logger.exception("Console command failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
