"""Test embedding on a real file."""
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from oracle.embedders.clap_embedder import CLAPEmbedder

# Test file
test_file = Path(r"A:\music\Active Music\A Day To Remember - A Day To Remember - The Downfall of Us All (Official Video) [CN4IIgFz93k].m4a")

if not test_file.exists():
    print(f"File not found: {test_file}")
    sys.exit(1)

print(f"Testing: {test_file.name}")
print(f"Size: {test_file.stat().st_size / 1024 / 1024:.1f} MB")

print("\nLoading CLAP model...")
embedder = CLAPEmbedder()
print(f"Model: {embedder.get_model_info()}")

print("\nEmbedding audio...")
try:
    vec = embedder.embed_audio(test_file)
    if vec is None:
        print("FAILED: embed_audio returned None")
    else:
        print(f"SUCCESS: {len(vec)}-dim embedding")
        print(f"First 5 values: {vec[:5]}")
except Exception as e:
    print(f"EXCEPTION: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
