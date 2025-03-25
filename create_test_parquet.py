import pandas as pd

# Create a small test dataset with URLs
df = pd.DataFrame({
    'url': [
        'https://www.google.com',
        'https://www.wikipedia.org',
        'https://www.example.com',
        'https://github.com',
        'https://www.python.org'
    ],
    'metadata': [
        'Google Homepage',
        'Wikipedia',
        'Example Domain',
        'GitHub',
        'Python.org'
    ]
})

# Save to parquet file
df.to_parquet('test_urls.parquet', index=False)
print(f"Created test parquet file with {len(df)} URLs")
