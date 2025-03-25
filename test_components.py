from glossapi import Corpus, GlossExtract, GlossSection, GlossSectionClassifier
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test directories
input_dir = "./test_data"
output_dir = "./test_output"

# Make sure output directory exists
os.makedirs(output_dir, exist_ok=True)

def test_corpus():
    logger.info("=== Testing Corpus ===")
    try:
        corpus = Corpus(
            input_dir=input_dir,
            output_dir=output_dir
        )
        logger.info("Corpus initialization successful")
        
        # Print package info
        logger.info(f"Package version: {corpus.__module__.split('.')[0]}")
        
        # Show model paths
        logger.info(f"Section classifier model path: {corpus.section_classifier_model_path}")
        logger.info(f"Extraction model path: {corpus.extraction_model_path}")
        
        return True
    except Exception as e:
        logger.error(f"Error in Corpus test: {e}")
        return False

def test_gloss_extract():
    logger.info("=== Testing GlossExtract ===")
    try:
        extractor = GlossExtract()
        logger.info("GlossExtract initialization successful")
        
        # Test acceleration settings
        extractor.enable_accel(threads=2, type="CPU")
        logger.info("Acceleration settings successful")
        
        # Create extractor
        extractor.create_extractor()
        logger.info("Extractor creation successful")
        
        return True
    except Exception as e:
        logger.error(f"Error in GlossExtract test: {e}")
        return False

def test_gloss_section():
    logger.info("=== Testing GlossSection ===")
    try:
        sectioner = GlossSection()
        logger.info("GlossSection initialization successful")
        return True
    except Exception as e:
        logger.error(f"Error in GlossSection test: {e}")
        return False

def test_gloss_section_classifier():
    logger.info("=== Testing GlossSectionClassifier ===")
    try:
        classifier = GlossSectionClassifier()
        logger.info("GlossSectionClassifier initialization successful")
        return True
    except Exception as e:
        logger.error(f"Error in GlossSectionClassifier test: {e}")
        return False

if __name__ == "__main__":
    results = {
        "Corpus": test_corpus(),
        "GlossExtract": test_gloss_extract(),
        "GlossSection": test_gloss_section(),
        "GlossSectionClassifier": test_gloss_section_classifier()
    }
    
    logger.info("\n=== Test Results ===")
    for component, success in results.items():
        status = "PASS" if success else "FAIL"
        logger.info(f"{component}: {status}")
