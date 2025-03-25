from glossapi import Corpus
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# Try to instantiate the Corpus class
try:
    print("Attempting to create Corpus instance...")
    corpus = Corpus(
        input_dir="./test_data",
        output_dir="./test_output"
    )
    print("Corpus instance created successfully")
except Exception as e:
    print(f"Error creating Corpus instance: {e}")

print("Script completed")
