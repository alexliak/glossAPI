#!/usr/bin/env python3
import asyncio
import aiohttp
import ssl
import os

async def fetch_url(url):
    """Fetch a URL and check if it's a PDF."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Cache-Control': 'max-age=0',
        'Upgrade-Insecure-Requests': '1',
    }
    
    timeout = aiohttp.ClientTimeout(total=30)
    sslcontext = ssl.create_default_context()
    sslcontext.check_hostname = False
    sslcontext.verify_mode = ssl.CERT_NONE
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, ssl=sslcontext) as response:
                print(f"URL: {url}")
                print(f"Status: {response.status}")
                print(f"Content-Type: {response.headers.get('Content-Type', 'Unknown')}")
                
                if response.status == 200:
                    content = await response.read()
                    content_start = content[:50]  # First 50 bytes
                    print(f"Content starts with: {content_start}")
                    
                    if content.startswith(b'%PDF-'):
                        print("This is a PDF file!")
                        # Save the PDF
                        filename = url.split('/')[-1]
                        with open(filename, 'wb') as f:
                            f.write(content)
                        print(f"Saved to {filename}")
                    else:
                        print("This is NOT a PDF file")
                        
                    # If it's HTML, try to find PDF links
                    if b'<html' in content[:1000] or b'<!DOCTYPE' in content[:1000]:
                        print("Content appears to be HTML. Looking for PDF links...")
                        text_content = content.decode('utf-8', errors='ignore')
                        
                        # Look for PDF links
                        import re
                        pdf_patterns = [
                            r'href="([^"]+\.pdf)"',
                            r'href="(/bitstream/[^"]+\.pdf)"',
                            r'href="(/retrieve/[^"]+\.pdf)"'
                        ]
                        
                        for pattern in pdf_patterns:
                            matches = re.findall(pattern, text_content)
                            if matches:
                                print(f"Found PDF links with pattern {pattern}:")
                                for i, match in enumerate(matches[:5]):  # Show only first 5
                                    if not match.startswith('http'):
                                        if match.startswith('/'):
                                            match = f"https://repository.kallipos.gr{match}"
                                        else:
                                            match = f"{url}/{match}"
                                    print(f"  {i+1}. {match}")
                                
                                if len(matches) > 5:
                                    print(f"  ...and {len(matches) - 5} more")
                
                # Save headers for inspection
                print("\nResponse Headers:")
                for header, value in response.headers.items():
                    print(f"  {header}: {value}")
                    
    except Exception as e:
        print(f"Error: {e}")

async def main():
    # IDs to check
    item_ids = [295, 562, 774, 513]
    
    # Common patterns for PDFs in the repository
    for item_id in item_ids:
        print(f"\n===== Testing item ID: {item_id} =====")
        
        # Test the handle URL
        handle_url = f"https://repository.kallipos.gr/handle/11419/{item_id}"
        await fetch_url(handle_url)
        
        # Test direct bitstream URLs
        common_filenames = [
            "00_master_document.pdf",
            "01_master_document.pdf", 
            "master_document.pdf",
            f"{item_id}.pdf",
            "document.pdf",
            "main.pdf",
            "book.pdf",
            "content.pdf",
            "fulltext.pdf"
        ]
        
        for filename in common_filenames:
            direct_url = f"https://repository.kallipos.gr/bitstream/11419/{item_id}/1/{filename}"
            print(f"\n----- Testing direct URL with {filename} -----")
            await fetch_url(direct_url)

if __name__ == "__main__":
    asyncio.run(main())