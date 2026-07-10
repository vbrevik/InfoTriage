"""Run opml-health as ``python -m apps.opml_health``."""
import asyncio
import argparse
from apps.opml_health.service import main as run_main

if __name__ == "__main__":
    asyncio.run(run_main())
