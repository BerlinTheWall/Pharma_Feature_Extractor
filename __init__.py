"""Pharma Monograph Extractor - Extract numerous features from pharmaceutical monographs."""

__version__ = "1.0.0"
__author__ = "Hooman katebpourshahidi"

from .metadata_extractor import extract_metadata
from .adverse_events_extractor import extract_adverse_events
from .drug_interactions_extractor import process_drug_interactions_folder, INTERACTIONS_OUTPUT_FOLDER
from .pipeline import run_pipeline

__all__ = [
    # 'extract_metadata',
    # 'extract_adverse_events', 
    # 'process_drug_interactions_folder',
    # 'INTERACTIONS_OUTPUT_FOLDER',
    'run_pipeline'
]