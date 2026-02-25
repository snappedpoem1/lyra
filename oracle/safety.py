"""
The Safety Doctrine - Transaction Logging & Time Travel

"Every move leaves a trace. Every trace can be reversed."

Features:
- Transaction journal (JSONL format)
- Plan-Execute pattern for all file operations
- Rollback support (undo last N operations)
- Zero-trust file handling

Author: Lyra Oracle v10.0
"""

<<<<<<< HEAD
import os
=======
>>>>>>> fc77b41 (Update workspace state and diagnostics)
import json
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict

from oracle.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# Journal location
JOURNAL_PATH = PROJECT_ROOT / "journal.jsonl"


@dataclass
class Transaction:
    """A single reversible file operation."""
    
    id: str                    # Unique transaction ID (timestamp-based)
    timestamp: str             # ISO 8601 timestamp
    action: str                # move, rename, delete, create
    source: Optional[str]      # Source path (before operation)
    target: Optional[str]      # Target path (after operation)
    backup: Optional[str]      # Backup location (for undo)
    metadata: Dict[str, Any]   # Additional context (size, hash, etc.)
    status: str                # planned, applied, failed, undone
    error: Optional[str]       # Error message if failed
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Transaction':
        """Create Transaction from dict."""
        return cls(**data)


class Journal:
    """The Timeline - logs every operation, enables time travel."""
    
    def __init__(self, path: Path = JOURNAL_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create journal if it doesn't exist
        if not self.path.exists():
            self.path.touch()
            logger.info(f"🌟 Journal initialized: {self.path}")
    
    def write(self, transaction: Transaction) -> None:
        """
        Append transaction to journal.
        JSONL format (one JSON object per line).
        """
        try:
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(transaction.to_dict()) + '\n')
            logger.debug(f"📝 Logged: {transaction.action} {transaction.source} → {transaction.target}")
        except Exception as e:
            logger.error(f"❌ Journal write failed: {e}")
            raise
    
    def read_all(self) -> List[Transaction]:
        """Read all transactions from journal."""
        transactions = []
        
        if not self.path.exists():
            return transactions
        
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        transactions.append(Transaction.from_dict(data))
                    except json.JSONDecodeError as e:
                        logger.warning(f"⚠️ Malformed journal entry: {e}")
                        continue
        except Exception as e:
            logger.error(f"❌ Journal read failed: {e}")
            raise
        
        return transactions
    
    def read_last(self, n: int = 1) -> List[Transaction]:
        """Read last N transactions (most recent first)."""
        all_txns = self.read_all()
        return list(reversed(all_txns[-n:]))
    
    def count(self) -> int:
        """Count total transactions."""
        return len(self.read_all())


class SafetyController:
    """
    The Guardian - enforces plan-execute workflow.
    
    "No file moves without a plan. No plan without a journal entry."
    """
    
    def __init__(self, journal: Optional[Journal] = None):
        self.journal = journal or Journal()
    
    def plan_operation(
        self,
        action: str,
        source: Optional[str] = None,
        target: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create an operation plan (doesn't execute).
        
        Returns a structured dict ("The Plan"):
        {
            "action": "move",
            "source": "downloads/track.flac",
            "target": "library/artist/track.flac",
            "safe": True,
            "warnings": [],
            "metadata": {...}
        }
        """
        plan = {
            "action": action,
            "source": source,
            "target": target,
            "safe": True,
            "warnings": [],
            "metadata": metadata or {}
        }
        
        # Validation checks
        if action in ["move", "rename", "delete"] and not source:
            plan["safe"] = False
            plan["warnings"].append("No source specified")
            return plan
        
        if action in ["move", "rename", "create"] and not target:
            plan["safe"] = False
            plan["warnings"].append("No target specified")
            return plan
        
        # Check if source exists
        if source:
            source_path = Path(source)
            if not source_path.exists():
                plan["safe"] = False
                plan["warnings"].append(f"Source does not exist: {source}")
        
        # Check if target already exists (collision)
        if target and action != "delete":
            target_path = Path(target)
            if target_path.exists():
                plan["warnings"].append(f"Target already exists (will overwrite): {target}")
        
        # Check disk space for moves/copies
        if action in ["move", "create"] and source:
            try:
                source_path = Path(source)
                if source_path.exists():
                    size_mb = source_path.stat().st_size / (1024 * 1024)
                    plan["metadata"]["size_mb"] = round(size_mb, 2)
                    
                    if target:
                        target_drive = Path(target).anchor
                        usage = shutil.disk_usage(target_drive or '.')
                        free_mb = usage.free / (1024 * 1024)
                        
                        if free_mb < size_mb + 100:  # Keep 100MB buffer
                            plan["safe"] = False
                            plan["warnings"].append(f"Insufficient disk space on {target_drive}")
            except Exception as e:
                plan["warnings"].append(f"Could not check disk space: {e}")
        
        logger.info(f"📋 Plan created: {action} → Safe={plan['safe']}")
        return plan
    
    def apply_plan(self, plan: Dict[str, Any]) -> Transaction:
        """
        Execute a plan and log to journal.
        
        Returns the completed Transaction.
        """
        action = plan["action"]
        source = plan["source"]
        target = plan["target"]
        metadata = plan.get("metadata", {})
        
        # Generate transaction ID
        txn_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        timestamp = datetime.now().isoformat()
        
        # Create backup path for undo
        backup_path = None
        if action in ["move", "delete"] and source:
            backup_dir = PROJECT_ROOT / ".safety_backups" / txn_id
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = str(backup_dir / Path(source).name)
        
        transaction = Transaction(
            id=txn_id,
            timestamp=timestamp,
            action=action,
            source=source,
            target=target,
            backup=backup_path,
            metadata=metadata,
            status="planned",
            error=None
        )
        
        # Check safety
        if not plan.get("safe", False):
            transaction.status = "failed"
            transaction.error = "Plan marked unsafe: " + "; ".join(plan.get("warnings", []))
            self.journal.write(transaction)
            logger.error(f"❌ Unsafe plan rejected: {transaction.error}")
            raise ValueError(transaction.error)
        
        # Execute operation
        try:
            if action == "move":
                self._execute_move(source, target, backup_path)
            elif action == "rename":
                self._execute_rename(source, target, backup_path)
            elif action == "delete":
                self._execute_delete(source, backup_path)
            elif action == "create":
                self._execute_create(target, metadata)
            else:
                raise ValueError(f"Unknown action: {action}")
            
            transaction.status = "applied"
            logger.info(f"✅ Applied: {action} {source} → {target}")
        
        except Exception as e:
            transaction.status = "failed"
            transaction.error = str(e)
            logger.error(f"❌ Operation failed: {e}")
        
        finally:
            # Always log to journal
            self.journal.write(transaction)
        
        return transaction
    
    def _execute_move(self, source: str, target: str, backup_path: Optional[str]) -> None:
        """Move file with backup."""
        source_path = Path(source)
        target_path = Path(target)
        
        # Create target directory
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Backup original
        if backup_path:
            shutil.copy2(source_path, backup_path)
        
        # Move
        shutil.move(str(source_path), str(target_path))
    
    def _execute_rename(self, source: str, target: str, backup_path: Optional[str]) -> None:
        """Rename file (same as move)."""
        self._execute_move(source, target, backup_path)
    
    def _execute_delete(self, source: str, backup_path: Optional[str]) -> None:
        """Delete file with backup."""
        source_path = Path(source)
        
        # Backup before delete
        if backup_path:
            shutil.copy2(source_path, backup_path)
        
        # Delete
        source_path.unlink()
    
    def _execute_create(self, target: str, metadata: Dict[str, Any]) -> None:
        """Create file/directory."""
        target_path = Path(target)
        
        if metadata.get("type") == "directory":
            target_path.mkdir(parents=True, exist_ok=True)
        else:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.touch()
    
    def undo_last(self, n: int = 1) -> List[Transaction]:
        """
        Undo last N operations using journal.
        
        "Rolling back the timeline..."
        """
        logger.info(f"⏪ Rolling back {n} operation(s)...")
        
        transactions = self.journal.read_last(n)
        undone = []
        
        for txn in transactions:
            if txn.status != "applied":
                logger.warning(f"⚠️ Skipping non-applied transaction: {txn.id}")
                continue
            
            try:
                self._undo_transaction(txn)
                
                # Log undo operation
                undo_txn = Transaction(
                    id=f"{txn.id}_undo",
                    timestamp=datetime.now().isoformat(),
                    action=f"undo_{txn.action}",
                    source=txn.target,
                    target=txn.source,
                    backup=None,
                    metadata={"original_txn": txn.id},
                    status="applied",
                    error=None
                )
                self.journal.write(undo_txn)
                undone.append(undo_txn)
                
                logger.info(f"✅ Undone: {txn.action} {txn.id}")
            
            except Exception as e:
                logger.error(f"❌ Undo failed for {txn.id}: {e}")
        
        return undone
    
    def _undo_transaction(self, txn: Transaction) -> None:
        """Reverse a single transaction."""
        if txn.action in ["move", "rename"]:
            # Restore from target back to source
            target_path = Path(txn.target)
            source_path = Path(txn.source)
            
            if target_path.exists():
                source_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target_path), str(source_path))
            elif txn.backup:
                # Restore from backup if target gone
                backup_path = Path(txn.backup)
                if backup_path.exists():
                    source_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_path, source_path)
        
        elif txn.action == "delete":
            # Restore from backup
            if txn.backup:
                backup_path = Path(txn.backup)
                source_path = Path(txn.source)
                
                if backup_path.exists():
                    source_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_path, source_path)
        
        elif txn.action == "create":
            # Delete the created file
            target_path = Path(txn.target)
            if target_path.exists():
                if target_path.is_dir():
                    shutil.rmtree(target_path)
                else:
                    target_path.unlink()


# ── Public API ──────────────────────────────────────────────

# Global safety controller instance
_controller = None


def get_controller() -> SafetyController:
    """Get global SafetyController instance."""
    global _controller
    if _controller is None:
        _controller = SafetyController()
    return _controller


def plan_operation(action: str, source: Optional[str] = None, target: Optional[str] = None, **metadata) -> Dict[str, Any]:
    """Create an operation plan."""
    return get_controller().plan_operation(action, source, target, metadata)


def apply_plan(plan: Dict[str, Any]) -> Transaction:
    """Execute a plan."""
    return get_controller().apply_plan(plan)


def undo_last(n: int = 1) -> List[Transaction]:
    """Undo last N operations."""
    return get_controller().undo_last(n)


def get_journal() -> Journal:
    """Get the global journal instance."""
    return get_controller().journal


# ── CLI Entry Point ─────────────────────────────────────────

def main():
    """CLI tool for safety operations."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m oracle.safety <command>")
        print("Commands:")
        print("  history [n]  - Show last N operations (default: 10)")
        print("  undo [n]     - Undo last N operations (default: 1)")
        return
    
    command = sys.argv[1]
    journal = get_journal()
    
    if command == "history":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        transactions = journal.read_last(n)
        
        print(f"📜 Last {n} operations:\n")
        for txn in transactions:
            status_icon = {"applied": "✅", "failed": "❌", "planned": "📋"}.get(txn.status, "⚪")
            print(f"{status_icon} [{txn.timestamp}] {txn.action}")
            print(f"   {txn.source} → {txn.target}")
            if txn.error:
                print(f"   Error: {txn.error}")
            print()
    
    elif command == "undo":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        undone = undo_last(n)
        print(f"⏪ Rolled back {len(undone)} operation(s)")
    
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
