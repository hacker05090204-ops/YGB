"""Adapter exports for async ingestion."""

import logging

from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.adapters.bugcrowd import BugcrowdAdapter
from backend.ingestion.adapters.cisa_kev import CISAKEVAdapter
from backend.ingestion.adapters.circl_cve import CIRCLCVEAdapter
from backend.ingestion.adapters.exploitdb import ExploitDBAdapter
from backend.ingestion.adapters.github_advisory import GitHubAdvisoryAdapter
from backend.ingestion.adapters.hackerone import HackerOneAdapter
from backend.ingestion.adapters.nvd import NVDAdapter
from backend.ingestion.adapters.osv import OSVAdapter

logger = logging.getLogger("ygb.ingestion.adapters")

__all__ = [
    "BugcrowdAdapter",
    "CISAKEVAdapter",
    "CIRCLCVEAdapter",
    "ExploitDBAdapter",
    "GitHubAdvisoryAdapter",
    "HackerOneAdapter",
    "NVDAdapter",
    "OSVAdapter",
]

MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
