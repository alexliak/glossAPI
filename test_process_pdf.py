from glossapi import Corpus
import logging
import os
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test directories
input_dir = "./downloads"
output_dir = "./processed_output"

# Make sure output directory exists
os.makedirs(output_dir, exist_ok=True)

def main():
    logger.info("=== Starting GlossAPI PDF processing test ===")
    
    # Initialize the Corpus processor
    corpus = Corpus(
        input_dir=input_dir,
        output_dir=output_dir
    )
    
    # Log the PDF files that will be processed
    pdf_files = list(Path(input_dir).glob("*.pdf"))
    logger.info(f"Found {len(pdf_files)} PDF files to process:")
    for pdf in pdf_files:
        logger.info(f"  - {pdf.name}")
    
    # Step 1: Extract PDFs to markdown (with OCR if needed)
    logger.info("Step 1: Extracting PDFs to markdown...")
    corpus.extract(input_format="pdf", num_threads=2)
    
    # Step 2: Extract sections from markdown files
    logger.info("Step 2: Extracting sections from markdown files...")
    corpus.section()
    
    # Step 3: Classify and annotate sections
    logger.info("Step 3: Classifying and annotating sections...")
    corpus.annotate()
    
    logger.info("=== Processing complete ===")
    logger.info(f"Results saved to {output_dir}")

if __name__ == "__main__":
    main()
