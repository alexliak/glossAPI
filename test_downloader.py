import argparse
import sys
import os
import pandas as pd
from pathlib import Path

# Add the pipeline/scripts directory to the Python path
sys.path.append(str(Path(__file__).parent / 'pipeline' / 'scripts'))

try:
    from concurrent_downloader import parse_args, generate_filename
    print("Successfully imported concurrent_downloader module")
    
    # Test generate_filename function
    print("\nTesting generate_filename function:")
    test_indices = [0, 1, 10, 100, 1000, 17576]  # 17576 = 26^3
    for idx in test_indices:
        filename = generate_filename(idx, "pdf")
        print(f"Index {idx} -> Filename: {filename}")
    
    # Test if parse_args function works
    print("\nTesting parse_args function:")
    # Save original sys.argv
    original_argv = sys.argv
    
    try:
        # Set up test arguments
        sys.argv = [
            "concurrent_downloader.py", 
            "--input-parquet", "test.parquet",
            "--url-column", "url", 
            "--output-dir", "./downloads"
        ]
        
        args = parse_args()
        print(f"Arguments parsed successfully: {args}")
    finally:
        # Restore original sys.argv
        sys.argv = original_argv
    
    print("\nAll tests completed successfully")
    
except ImportError as e:
    print(f"Error importing concurrent_downloader: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Error during testing: {e}")
    sys.exit(1)
