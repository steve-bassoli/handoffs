"""Use the shared engine from the source checkout; executors receive its standalone copy."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.complexity import main

if __name__ == '__main__':
    main()
