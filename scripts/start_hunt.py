#!/usr/bin/env python3
"""Start a bug bounty hunt.

Usage:
    python scripts/start_hunt.py --target https://example.com --scope "*.example.com"
    python scripts/start_hunt.py --target https://api.example.com --scope "api.example.com,*.example.com" --max-pages 50
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def main():
    parser = argparse.ArgumentParser(
        description="Pure AI Hunter Agent - Autonomous Bug Bounty Hunter"
    )
    parser.add_argument(
        "--target", required=True, help="Target URL (e.g., https://example.com)"
    )
    parser.add_argument(
        "--scope",
        required=True,
        help="Comma-separated scope rules (e.g., '*.example.com,example.com')",
    )
    parser.add_argument(
        "--program", default="Unknown Program", help="Bug bounty program name"
    )
    parser.add_argument(
        "--max-pages", type=int, default=150, help="Maximum pages to explore (default: 150)"
    )
    parser.add_argument(
        "--max-rpm",
        type=int,
        default=20,
        help="Maximum requests per minute (default: 20)",
    )
    parser.add_argument(
        "--max-payloads",
        type=int,
        default=10,
        help="Maximum payloads per parameter (default: 10)",
    )
    parser.add_argument(
        "--no-reflection",
        action="store_true",
        help="Disable self-reflection on failures",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/ssd/reports"),
        help="Output directory for reports",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger("ygb.hunter.cli")

    # Parse scope rules
    scope_rules = [s.strip() for s in args.scope.split(",")]

    logger.info("=" * 70)
    logger.info("YGB PURE AI HUNTER AGENT")
    logger.info("=" * 70)
    logger.info("Target: %s", args.target)
    logger.info("Scope: %s", scope_rules)
    logger.info("Program: %s", args.program)
    logger.info("Max Pages: %d", args.max_pages)
    logger.info("Max RPM: %d", args.max_rpm)
    logger.info("Reflection: %s", "Enabled" if not args.no_reflection else "Disabled")
    logger.info("=" * 70)

    # Create hunt configuration
    from backend.hunter.hunter_agent import HuntConfig, PureAIHunterAgent

    config = HuntConfig(
        target=args.target,
        scope_rules=scope_rules,
        program_name=args.program,
        max_pages=args.max_pages,
        max_payloads_per_param=args.max_payloads,
        max_rpm=args.max_rpm,
        enable_reflection=not args.no_reflection,
        output_dir=args.output_dir,
    )

    # Initialize hunter
    hunter = PureAIHunterAgent(config)

    try:
        # Start hunt
        result = await hunter.hunt()

        # Display results
        logger.info("")
        logger.info("=" * 70)
        logger.info("HUNT RESULTS")
        logger.info("=" * 70)
        logger.info("Session ID: %s", result.session_id)
        logger.info("Duration: %.1f seconds", result.duration_seconds)
        logger.info("Pages Explored: %d", result.pages_explored)
        logger.info("Endpoints Tested: %d", result.endpoints_tested)
        logger.info("Payloads Sent: %d", result.payloads_sent)
        logger.info("Reflection Cycles: %d", result.reflection_cycles)
        logger.info("Approvals Required: %d", result.approvals_required)
        logger.info("Approvals Granted: %d", result.approvals_granted)
        logger.info("")
        logger.info("FINDINGS: %d", len(result.findings))
        logger.info("=" * 70)

        if result.findings:
            logger.info("")
            logger.info("Vulnerabilities Found:")
            for finding in result.findings:
                logger.info(
                    "  [%s] %s - %s (CVSS: %.1f, Confidence: %.0f%%)",
                    finding.severity,
                    finding.finding_id,
                    finding.title,
                    finding.cvss_score,
                    finding.confidence * 100,
                )

            logger.info("")
            logger.info("Summary Report: %s", result.summary_report_path)
            logger.info("")
            logger.info("Individual reports saved to: %s", config.output_dir)
        else:
            logger.info("")
            logger.info("No vulnerabilities found.")
            logger.info("This could mean:")
            logger.info("  - The target is well-secured")
            logger.info("  - WAF/firewall blocked testing")
            logger.info("  - Scope was too limited")
            logger.info("  - More advanced techniques needed")

        logger.info("=" * 70)

        return 0 if result.findings else 1

    except KeyboardInterrupt:
        logger.warning("Hunt interrupted by user")
        return 130
    except Exception as e:
        logger.error("Hunt failed: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
