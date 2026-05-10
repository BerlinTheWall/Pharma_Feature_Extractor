"""Main entry point for the pharmaceutical monograph extractor."""

import sys
import os
import winsound

# Add parent directory to path if running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pharma_extractor_package.pipeline import run_pipeline

if __name__ == "__main__":
    # IMPORTANT: Change this to your PDF folder path!
    target_folder = "../Received Monographs/Product monograph/ACE Inhibitor - Copy/Cilazapril"
    
    # Run the pipeline
    run_pipeline(target_folder)
    
    # Play completion sound
    winsound.Beep(440, 500)
    print("\n✨ Pipeline complete!")