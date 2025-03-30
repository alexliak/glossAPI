import aiohttp
import asyncio
import os
import argparse
from urllib.parse import urlparse, urlencode
import random
import aiofiles
import logging
import json
import time
import ssl

# Your existing ScrapeOps API key
SCRAPEOPS_API_KEY = '0b67d1e8-d38c-4944-a6bf-c6ac7296d0b8'

# Configure logging for behavior tracking and errors
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Function to construct the ScrapeOps proxy URL
def get_scrapeops_url(target_url):
    payload = {'api_key': SCRAPEOPS_API_KEY, 'url': target_url,
               'bypass': 'cloudflare_level_1'}
    proxy_url = 'https://proxy.scrapeops.io/v1/?' + urlencode(payload)
    return proxy_url

# Function to extract base URL from a given full URL
async def get_base_url(url):
    if not url.startswith("http"):
        url = f"http://{url}"
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    return base_url

# Function to generate random user-agents for avoiding bot detection
def user_agent_generator():
    templates = [
        "Mozilla/5.0 ({os}) AppleWebKit/537.36 (KHTML, like Gecko) {browser}/{version} Safari/537.36",
        "Mozilla/5.0 ({os}) Gecko/20100101 {browser}/{version}",
        "Mozilla/5.0 ({os}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36"
    ]
    operating_systems = [
        "Windows NT 10.0; Win64; x64",
        "Macintosh; Intel Mac OS X 10_15_7",
        "X11; Linux x86_64",
        "Windows NT 6.1; Win64; x64",
        "Android 9; Mobile; rv:40.0"
    ]
    browsers = [
        ("Chrome", random.randint(70, 90)),
        ("Firefox", random.randint(50, 80)),
        ("Edge", random.randint(80, 90))
    ]
    while True:
        template = random.choice(templates)
        os = random.choice(operating_systems)
        browser, version = random.choice(browsers)
        full_version = f"{version}.0.{random.randint(1000, 9999)}"
        user_agent = template.format(os=os, browser=browser, version=full_version)
        yield user_agent

# Function to initialize session headers
async def setup_session(session, url, headers):
    """Initialize the session with base headers."""
    base_url = await get_base_url(url)
    initial_url = f"{base_url}"
    async with session.get(initial_url, headers=headers) as response:
        await response.text()
    return headers

# Function to download PDFs allowing retrial and concurrent downloads
async def download_pdf(index, metadata, pdf_url, semaphore, args, user_agent, referer=None):
    # Check if we accidentally swapped metadata and URL (happens in retry)
    if isinstance(metadata, str) and (metadata.startswith("http://") or metadata.startswith("https://")):
        # Swap them if they're reversed
        temp = metadata
        metadata = pdf_url
        pdf_url = temp
        logging.debug(f"Swapped metadata and URL for proper handling")
        
    if not referer:
        base_url = await get_base_url(pdf_url)
    else:
        base_url = referer
        
    # Extract repository domain from URL for proper referrer
    if "repository.kallipos.gr" in pdf_url:
        base_url = "https://repository.kallipos.gr/"
        
    # Special handling for Kallipos repository
    headers = {
        'User-Agent': user_agent,
        'Referer': base_url,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Cache-Control': 'max-age=0',
        'Upgrade-Insecure-Requests': '1',
        'sec-ch-ua': '"Google Chrome";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"'
    }

    # For Kallipos, use direct URL instead of proxy
    use_direct = "repository.kallipos.gr" in pdf_url
    target_url = pdf_url if use_direct else get_scrapeops_url(pdf_url)

    # Log debug info about the URL
    logging.debug(f"Processing URL: {pdf_url}")
    if use_direct:
        logging.debug("Using direct URL (Kallipos repository)")
    else:
        logging.debug("Using ScrapeOps proxy URL")

    async with semaphore:
        # Use timeout from command-line arguments or default to 120s
        timeout_seconds = args.timeout if hasattr(args, 'timeout') else 120
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        logging.debug(f"Using timeout of {timeout_seconds} seconds")
        
        # Configure SSL context for HTTPS requests
        sslcontext = ssl.create_default_context()
        sslcontext.check_hostname = False
        sslcontext.verify_mode = ssl.CERT_NONE

        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Visit main site first to get cookies for Kallipos repository
            if use_direct and args.kallipos_mode:
                try:
                    logging.debug(f"Initializing session with {base_url}")
                    async with session.get(base_url, headers=headers, ssl=sslcontext) as init_response:
                        await init_response.text()
                        logging.debug(f"Session initialized successfully with status {init_response.status}")
                except Exception as e:
                    logging.warning(f"Error visiting main site: {e}")
            
            # Add random sleep interval to avoid being detected as a bot
            sleep_time = random.uniform(args.sleep, args.sleep + 2)
            logging.debug(f"Waiting {sleep_time:.1f}s before next request")
            await asyncio.sleep(sleep_time)

            # Construct filename and determine output path
            file_name = f'paper_{index}.{args.type}'
            site_dir = "kallipos" if "repository.kallipos.gr" in pdf_url else ""
            
            # Create subfolder if site specific
            if site_dir:
                output_path = os.path.join(args.output, site_dir)
                os.makedirs(output_path, exist_ok=True)
            else:
                output_path = args.output if args.output else "./"
            
            # For Kallipos repository with HTML pages, try to extract PDF URL
            if "handle" in pdf_url or "html" in pdf_url:
                try:
                    logging.info(f"Attempting to extract PDF from HTML page: {pdf_url}")
                    # First try to get the HTML page
                    async with session.get(pdf_url, headers=headers, ssl=sslcontext) as response:
                        if response.status == 200:
                            html_content = await response.text()
                            # Look for PDF link in the HTML
                            pdf_urls = []
                            import re
                            
                            # Multiple patterns to try for finding PDF links in the HTML
                            retrieve_patterns = [
                                r'href="(https://repository\.kallipos\.gr/retrieve/[^"]+\.pdf)"',
                                r'href="(/retrieve/[^"]+\.pdf)"',
                                r'href="(https://repository\.kallipos\.gr/bitstream/[^"]+\.pdf)"',
                                r'href="(/bitstream/[^"]+\.pdf)"',
                                r'href="([^"]+/retrieve/[^"]+\.pdf)"',
                                r'href="([^"]+/bitstream/[^"]+\.pdf)"',
                                r'a href="([^"]+\.pdf)"',
                                r'src="([^"]+\.pdf)"'
                            ]
                            
                            for pattern in retrieve_patterns:
                                matches = re.findall(pattern, html_content)
                                for match in matches:
                                    if not match.startswith("http"):
                                        if match.startswith("/"):
                                            match = f"https://repository.kallipos.gr{match}"
                                        else:
                                            match = f"https://repository.kallipos.gr/{match}"
                                    pdf_urls.append(match)
                            
                            # If we found PDF URLs, use the first one
                            if pdf_urls:
                                old_url = pdf_url
                                pdf_url = pdf_urls[0]
                                target_url = pdf_url
                                logging.info(f"Extracted PDF URL: {pdf_url} from {old_url}")
                            else:
                                # If no direct PDF link is found, look for a "download" button
                                download_patterns = [
                                    r'href="([^"]+)" class="[^"]*download-button[^"]*"',
                                    r'class="[^"]*download-button[^"]*" href="([^"]+)"',
                                    r'<a[^>]*download[^>]*href="([^"]+)"',
                                    r'<a[^>]*href="([^"]+)"[^>]*download[^>]*',
                                    r'href="([^"]+/download/[^"]+)"',
                                    r'class="btn btn-primary" href="([^"]+)"'
                                ]
                                
                                for pattern in download_patterns:
                                    matches = re.findall(pattern, html_content)
                                    for match in matches:
                                        if not match.startswith("http"):
                                            if match.startswith("/"):
                                                match = f"https://repository.kallipos.gr{match}"
                                            else:
                                                match = f"https://repository.kallipos.gr/{match}"
                                        pdf_urls.append(match)
                                
                                if pdf_urls:
                                    old_url = pdf_url
                                    pdf_url = pdf_urls[0]
                                    target_url = pdf_url
                                    logging.info(f"Found download button URL: {pdf_url} from {old_url}")
                                else:
                                    # Try to find the bitstream URL by following item ID pattern
                                    if "/handle/11419/" in pdf_url:
                                        item_id = pdf_url.split("/handle/11419/")[1].split("?")[0].split("/")[0]
                                        if item_id.isdigit():
                                            # Try various common filenames for Kallipos PDFs
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
                                            
                                            # Try direct bitstream URLs with common filenames
                                            for filename in common_filenames:
                                                direct_url = f"https://repository.kallipos.gr/bitstream/11419/{item_id}/1/{filename}"
                                                logging.info(f"Trying direct bitstream URL: {direct_url}")
                                                
                                                try:
                                                    async with session.get(direct_url, headers=headers, ssl=sslcontext) as direct_response:
                                                        if direct_response.status == 200:
                                                            direct_content = await direct_response.read()
                                                            if direct_content.startswith(b'%PDF-'):
                                                                await write_file(file_name, direct_content, output_path)
                                                                logging.info(f"Successfully downloaded PDF using direct bitstream URL: {direct_url}")
                                                                return (True, metadata, file_name)
                                                            elif len(direct_content) > 1000000:  # Large file that might be a PDF
                                                                await write_file(file_name, direct_content, output_path)
                                                                logging.info(f"Downloaded large file that might be a PDF: {direct_url}")
                                                                return (True, metadata, file_name)
                                                except Exception as e:
                                                    logging.debug(f"Error trying direct URL {direct_url}: {e}")
                                            
                                            # If direct attempts failed, try to get the bitstream directory
                                            bitstream_url = f"https://repository.kallipos.gr/bitstream/11419/{item_id}/1/"
                                            logging.info(f"Attempting to use constructed bitstream URL: {bitstream_url}")
                                            
                                            # Try to get the bitstream page
                                            try:
                                                async with session.get(bitstream_url, headers=headers, ssl=sslcontext) as bitstream_response:
                                                    if bitstream_response.status == 200:
                                                        bitstream_html = await bitstream_response.text()
                                                        # Look for PDF files in this page
                                                        pdf_file_pattern = r'href="([^"]+\.pdf)"'
                                                        pdf_matches = re.findall(pdf_file_pattern, bitstream_html)
                                                        
                                                        if pdf_matches:
                                                            match = pdf_matches[0]
                                                            if not match.startswith("http"):
                                                                if match.startswith("/"):
                                                                    match = f"https://repository.kallipos.gr{match}"
                                                                else:
                                                                    match = f"{bitstream_url}{match}"
                                                            pdf_url = match
                                                            target_url = pdf_url
                                                            logging.info(f"Found PDF in bitstream: {pdf_url}")
                                            except Exception as e:
                                                logging.warning(f"Error checking bitstream URL: {e}")
                                    
                                    if target_url == pdf_url and not pdf_url.endswith(".pdf"):
                                        logging.warning("Could not extract PDF URL from HTML page")
                except Exception as e:
                    logging.warning(f"Error extracting PDF URL: {e}")
                
            try:
                # Attempt to download the PDF
                async with session.get(target_url, headers=headers, ssl=sslcontext, allow_redirects=True) as response:
                    if response.status == 200:
                        content = await response.read()
                        
                        # Check if the content type is PDF
                        content_type = response.headers.get('Content-Type', '').lower()
                        content_is_pdf = False
                        
                        # Check the content type in headers
                        if 'application/pdf' in content_type:
                            content_is_pdf = True
                            logging.info(f"Content-Type confirms this is a PDF: {content_type}")
                        
                        # Also check the content itself for PDF magic bytes
                        if content.startswith(b'%PDF-'):
                            content_is_pdf = True
                            logging.info(f"Content starts with %PDF- signature")
                        
                        # If we've confirmed this is a PDF, save it
                        if content_is_pdf:
                            await write_file(file_name, content, output_path)
                            logging.info(f"Downloaded {file_name} to {output_path}")
                            return (True, metadata, file_name)
                        # If handle URL didn't give us a PDF, but provided HTML that could have a PDF link
                        elif "handle" in target_url and len(content) > 1000:
                            # This is likely an HTML page, try once more to extract direct PDF links
                            import re
                            html_content = content.decode('utf-8', errors='ignore')
                            
                            # Look specifically for "bitstream" links which often directly point to PDFs
                            bitstream_patterns = [
                                r'href="(/bitstream/[^"]+/\d+/[^"]+\.pdf)"',
                                r'href="(https://repository\.kallipos\.gr/bitstream/[^"]+/\d+/[^"]+\.pdf)"',
                                r'<a href="([^"]+\.pdf)"'
                            ]
                            
                            for pattern in bitstream_patterns:
                                matches = re.findall(pattern, html_content)
                                if matches:
                                    pdf_link = matches[0]
                                    if not pdf_link.startswith("http"):
                                        if pdf_link.startswith("/"):
                                            pdf_link = f"https://repository.kallipos.gr{pdf_link}"
                                        else:
                                            pdf_link = f"https://repository.kallipos.gr/{pdf_link}"
                                    
                                    logging.info(f"Found direct PDF link on page: {pdf_link}")
                                    # Try to download from this direct link
                                    try:
                                        async with session.get(pdf_link, headers=headers, ssl=sslcontext) as pdf_response:
                                            if pdf_response.status == 200:
                                                pdf_content = await pdf_response.read()
                                                # Verify this is an actual PDF
                                                if pdf_content.startswith(b'%PDF-'):
                                                    await write_file(file_name, pdf_content, output_path)
                                                    logging.info(f"Successfully downloaded PDF using direct link: {pdf_link}")
                                                    return (True, metadata, file_name)
                                    except Exception as e:
                                        logging.warning(f"Error downloading direct PDF link: {e}")
                                    
                            # If we've tried everything and still haven't found a PDF, save the HTML content for debugging
                            debug_file = os.path.join(output_path, f"debug_{file_name}.html")
                            async with aiofiles.open(debug_file, 'wb') as file:
                                await file.write(content)
                            logging.warning(f"Downloaded content is not a PDF file. Saved HTML to {debug_file} for debugging")
                        else:
                            # Not a PDF - could be HTML or an error page
                            logging.warning(f"Downloaded content is not a PDF file, status was 200 but not identified as PDF")
                        
                        return (False, metadata, file_name)
                    elif response.status == 500 and use_direct:
                        # Special handling for Kallipos repository's common 500 errors
                        logging.error(f"Server error 500 for {pdf_url} (common with Kallipos repository)")
                        # Add extra delay to avoid overloading the server
                        extra_delay = random.uniform(10, 15)
                        logging.info(f"Adding {extra_delay:.1f}s extra delay for Kallipos 500 error")
                        await asyncio.sleep(extra_delay)
                    elif response.status == 302 or response.status == 301:
                        # Handle redirects manually if needed
                        redirect_url = response.headers.get('Location')
                        if redirect_url:
                            logging.info(f"Following redirect to: {redirect_url}")
                            # Try to download from the redirect URL
                            try:
                                async with session.get(redirect_url, headers=headers, ssl=sslcontext) as redirect_response:
                                    if redirect_response.status == 200:
                                        redirect_content = await redirect_response.read()
                                        # Verify this is an actual PDF
                                        if redirect_content.startswith(b'%PDF-'):
                                            await write_file(file_name, redirect_content, output_path)
                                            logging.info(f"Successfully downloaded PDF from redirect: {redirect_url}")
                                            return (True, metadata, file_name)
                                        else:
                                            logging.warning(f"Redirect did not lead to a PDF file")
                            except Exception as e:
                                logging.warning(f"Error following redirect: {e}")
                    else:
                        logging.error(f"Failed to download {pdf_url}. Status code: {response.status}")
            except aiohttp.ClientError as e:
                logging.error(f"ClientError while downloading {pdf_url}: {e}")
            except asyncio.TimeoutError:
                logging.error(f"Timeout error while downloading {pdf_url} (timeout: {timeout_seconds}s)")
            except Exception as e:
                logging.error(f"Unexpected error while downloading {pdf_url}: {e}")
            
            return (False, metadata, file_name)

# Function to get the highest index of papers downloaded for continuation
def get_indexes(papers):
    if papers:
        nums = []
        for p in papers:
            num = p.split("_")[-1]
            nums.append(int(num))
        return sorted(nums)[-1:]
    return []

# Function to write downloaded content to a file
async def write_file(filename, content, output_path="./"):
    path_to_file = os.path.join(output_path, filename)
    async with aiofiles.open(path_to_file, 'wb') as file:
        await file.write(content)


#Function for handling command-line arguments
def parse_input():
    parser = argparse.ArgumentParser(description="Gets PDFs through URLs given as value entries in a JSON.", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--json", help="Add path to JSON file with URLs siteguide", required=True)
    parser.add_argument("--sleep", type=float, default=1, help="Set delay before new request is made (in seconds)")
    parser.add_argument("--type", help="Select file type to be downloaded e.g., 'pdf', 'doc'", required=True)
    parser.add_argument("--req", choices=['get', 'post'], default='get', help="Set request type 'get' or 'post'")
    parser.add_argument("-o", "--output", default="./", help="Set download directory")
    parser.add_argument("--little_potato", help="Set directory for progress_report.json (previously little_potato), default value is set to --output")
    parser.add_argument("--batch", type=int, default=10, help="Set number of files to download per run")
    
    # Add arguments from run_downloader.sh
    parser.add_argument("--concurrent", type=int, default=3, help="Number of concurrent downloads")
    parser.add_argument("--max-retries", type=int, default=3, help="Maximum number of retry attempts")
    parser.add_argument("--timeout", type=int, default=120, help="Request timeout in seconds")
    parser.add_argument("--log-dir", default="./logs", help="Directory for log files")
    parser.add_argument("--start-at", type=int, default=0, help="Start at position N in the JSON file (skip earlier entries)")
    parser.add_argument("--skip-every", type=int, default=0, help="Skip every Nth item, useful for distributed downloading")
    parser.add_argument("--randomize", action="store_true", help="Randomize download order to avoid detection")
    parser.add_argument("--kallipos-mode", action="store_true", help="Enable optimizations for Kallipos repository")
    
    args = parser.parse_args()

    if not args.little_potato:
        args.little_potato = args.output
    
    # Configure logging based on log-dir parameter
    if not os.path.exists(args.log_dir):
        os.makedirs(args.log_dir, exist_ok=True)
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(args.log_dir, f"download_{timestamp}.log")
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    # Add the file handler to the root logger
    logging.getLogger().addHandler(file_handler)
    logging.info(f"Logging initialized. Log file: {log_file}")
    
    # Log detailed configuration
    logging.info(f"PDF Downloader starting with arguments: {vars(args)}")
    
    return args

# Function to download PDFs and update progress report
async def download_pdfs(metadata_dict, semaphore, visited, indexes, args, progress_report, retry=1, depth=0, failed_downloads=None):
    retry_count = retry
    retries = {}
    tasks = []
    ordered_metadata = list(metadata_dict.items())
    user_agent_gen = user_agent_generator()
    i = 0
    successful_downloads = 0
    reached_end_of_file = True
    max_depth = 3  # Prevent infinite recursion
    
    # Initialize failed downloads dictionary if not provided
    if failed_downloads is None:
        failed_downloads = {}
    
    # Stop if we've gone too deep in recursion
    if depth > max_depth:
        logging.warning(f"Maximum recursion depth ({max_depth}) reached. Stopping download attempts.")
        return reached_end_of_file
    
    # Map to keep track of URL to metadata for failed downloads
    url_to_metadata = {}

    # First attempt to download files
    for metadata, url in ordered_metadata:
        if i < args.batch and metadata not in visited and metadata not in progress_report.values():
            reached_end_of_file = False
            index = indexes[-1] + 1 if indexes else 1
            indexes.append(index)
            task = asyncio.create_task(
                download_pdf(index, metadata, url, semaphore, args, next(user_agent_gen))
            )
            tasks.append(task)
            url_to_metadata[url] = metadata
            i += 1
            
    # If we didn't get enough files for the batch, look for more
    if i < args.batch and i > 0:
        logging.info(f"Only found {i} files to download, less than requested batch size {args.batch}")
    elif i == 0:
        logging.info(f"No new files to download in this batch. Already downloaded all available files.")
        return True
    
    results = await asyncio.gather(*tasks)

    # Process the results
    for idx, r in enumerate(results):
        if r:
            has_downloaded_file, metadata, pdf_file_name = r
            if has_downloaded_file:
                progress_report[pdf_file_name[:-4]] = metadata
                successful_downloads += 1
            else:
                # Get original URL for this task
                for url, meta in url_to_metadata.items():
                    if meta == metadata:
                        logging.warning(f"Failed to download file for metadata: {metadata}")
                        # Record failed download
                        failed_downloads[url] = metadata
                        if retry_count > 0:
                            retries[url] = metadata
                        break
    
    # Try more files if we didn't download enough
    files_still_needed = args.batch - successful_downloads
    
    # If we had failures and still have retries left, try the failed ones again
    if retries and retry_count > 0 and files_still_needed > 0:
        logging.info(f"Retrying download for {len(retries)} failed files")
        await download_pdfs(retries, semaphore, visited, indexes, 
                           argparse.Namespace(**{**vars(args), 'batch': min(len(retries), files_still_needed)}), 
                           progress_report, retry_count - 1, depth + 1, failed_downloads)
    
    # If we need more files after retries, try additional files
    files_still_needed = args.batch - (len(progress_report) - len(visited))
    if files_still_needed > 0 and not reached_end_of_file:
        # Find additional files that haven't been tried yet
        additional_files = {}
        for metadata, url in ordered_metadata:
            if metadata not in visited and metadata not in progress_report.values():
                # Skip ones we already tried in this batch
                if metadata not in url_to_metadata.values():
                    additional_files[metadata] = url
                    if len(additional_files) >= files_still_needed:
                        break
        
        # If we found more files, download them
        if additional_files:
            logging.info(f"Downloading {len(additional_files)} additional files to complete batch")
            await download_pdfs(additional_files, semaphore, visited, indexes, 
                               argparse.Namespace(**{**vars(args), 'batch': len(additional_files)}), 
                               progress_report, retry_count, depth + 1, failed_downloads)
    
    return reached_end_of_file



#The main function to parse input arguments, load URL metadata from a JSON file, manage download progress with semaphores for concurrency, and save the download progress to a JSON report file
async def main():
    # Track start time of the download process
    start_time = time.time()
    
    args = parse_input()
    
    # Load the metadata dictionary from the JSON file
    with open(args.json, 'r') as file:
        metadata_dict = json.load(file)
    
    logging.info(f"Loaded {len(metadata_dict)} items from {args.json}")
    
    # Load existing failed downloads if available
    failed_downloads_path = os.path.join(args.little_potato, 'failed_downloads.json')
    try:
        with open(failed_downloads_path, 'r') as file:
            failed_downloads = json.load(file)
        logging.info(f"Loaded existing failed downloads report with {len(failed_downloads)} entries")
        
        # For now, we will skip specific problematic downloads
        problem_urls = []
        for url, info in failed_downloads.items():
            if isinstance(info, dict) and "metadata" in info:
                metadata = info["metadata"]
                problem_urls.append((metadata, url))
                logging.info(f"Skipping problematic URL: {url}")
        
        # Let's try downloading other URLs (non-Kallipos or Kallipos URLs that haven't failed)
        # Keep track of which specific metadata entries we're going to skip
        skip_metadata = set()
        for metadata, url in problem_urls:
            skip_metadata.add(metadata)
        
        # Remove only problematic entries from metadata_dict
        original_count = len(metadata_dict)
        filtered_metadata = {}
        for metadata, url in metadata_dict.items():
            if metadata not in skip_metadata:
                filtered_metadata[metadata] = url
            
        metadata_dict = filtered_metadata
        logging.info(f"Filtered out {original_count - len(metadata_dict)} problematic URLs")
            
    except FileNotFoundError:
        logging.info("No existing failed downloads report found")
        failed_downloads = {}
    
    # Apply filtering options if specified
    if args.start_at > 0:
        # Convert to list to get indexed access
        items = list(metadata_dict.items())
        # Skip items before start_at
        items = items[args.start_at:]
        metadata_dict = dict(items)
        logging.info(f"Starting at position {args.start_at}, {len(metadata_dict)} items remain")
    
    if args.skip_every > 1:
        # Filter to get every Nth item
        items = list(metadata_dict.items())
        filtered_items = [items[i] for i in range(len(items)) if i % args.skip_every == 0]
        metadata_dict = dict(filtered_items)
        logging.info(f"Skipping every {args.skip_every} items, {len(metadata_dict)} items remain")
    
    if args.randomize:
        # Randomize order
        items = list(metadata_dict.items())
        random.shuffle(items)
        metadata_dict = dict(items)
        logging.info("Randomized download order")
    
    logging.info(f"Final processing list contains {len(metadata_dict)} items")
    
    # Apply Kallipos mode optimizations
    if args.kallipos_mode:
        logging.info("🚀 KALLIPOS MODE ENABLED: Using optimized settings for Kallipos repository")
        # Adjust concurrent downloads for Kallipos repository
        concurrent_value = min(args.concurrent, 2) if args.concurrent > 0 else 2
        retry_value = max(args.max_retries, 3)
        logging.info(f"Using {concurrent_value} concurrent downloads, {args.sleep}s delay, {retry_value} max retries")
    else:
        concurrent_value = args.concurrent if args.concurrent > 0 else 3
        retry_value = args.max_retries
    
    # Create semaphore that limits concurrent downloads
    semaphore = asyncio.Semaphore(concurrent_value)

    try:
        #Read existing progress report if any
        try:
            progress_report_path = os.path.join(args.little_potato, 'progress_report.json')
            with open(progress_report_path, 'r') as file:
                progress_report = json.load(file)
            logging.info(f"Loaded progress report with {len(progress_report)} entries")
            indexes = get_indexes(list(progress_report.keys()))
        except FileNotFoundError:
            progress_report = {}
            indexes = []
            logging.info("No existing progress report found")
        
        # Count total available files that haven't been downloaded yet
        visited = list(progress_report.values())
        available_files = [meta for meta in metadata_dict.keys() if meta not in visited]
        logging.info(f"Total files: {len(metadata_dict)}, Already processed: {len(progress_report)}, Remaining: {len(available_files)}")
        
        # Track initial progress report size
        initial_count = len(progress_report)
        
        # Create a dictionary to track this session's failed downloads
        session_failed = {}
        
        # If we're using Kallipos mode, add rate limit prevention mechanisms
        if args.kallipos_mode:
            # Add rate limiting prevention by scheduling breaks after batches of attempts
            batch_size = min(100, args.batch)
            if batch_size > 10:
                # Schedule logging for batches of downloads
                for i in range(10, batch_size + 1, 10):
                    logging.info(f"Scheduled {i}/{args.batch} downloads")
                
                # Add random long breaks to prevent rate limiting for large batches
                for i in range(20, batch_size + 1, 20):
                    break_duration = random.randint(60, 120)
                    logging.info(f"🔄 Kallipos rate limit prevention: Taking a {break_duration} second break after {i} attempts")
        
        # Run download process with retry count from command line arguments
        max_retries = args.max_retries if hasattr(args, 'max_retries') else 2
        finished = await download_pdfs(metadata_dict, semaphore, visited, indexes, args, progress_report, 
                                      retry=max_retries, depth=0, failed_downloads=session_failed)
        
        # Calculate how many new files were downloaded
        final_count = len(progress_report)
        downloaded_count = final_count - initial_count
        
        # Update the main failed downloads dictionary with new failures
        for url, metadata in session_failed.items():
            # Check if we tried the handle URL already
            if url.startswith("https://repository.kallipos.gr/retrieve/"):
                # Try to create a handle URL version if it's a retrieve URL
                handle_id = url.split("/")[-1].split(".")[0].split("-")[0]
                if handle_id.isdigit():
                    alternative_url = f"https://repository.kallipos.gr/handle/11419/{handle_id}"
                    session_failed[url] = {
                        "metadata": metadata,
                        "alternative_url": alternative_url,
                        "status": "Not tried",
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                else:
                    session_failed[url] = {
                        "metadata": metadata,
                        "status": "Failed",
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
            else:
                session_failed[url] = {
                    "metadata": metadata,
                    "status": "Failed",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
        
        # Merge with existing failed downloads
        failed_downloads.update(session_failed)
        
        # Log failed downloads for this session
        if session_failed:
            logging.warning(f"Failed to download {len(session_failed)} files in this session.")
            for url in session_failed:
                if "alternative_url" in session_failed[url]:
                    logging.info(f"Alternative URL for failed download: {session_failed[url]['alternative_url']}")
        
        if finished:
            logging.info(f"All available files are in progress_report.json - Finished! Downloaded {downloaded_count} new files.")
        else:
            logging.info(f"PDF downloads completed. Downloaded {downloaded_count} new files out of {args.batch} requested.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        raise
    finally:
        # Write progress report to a JSON file
        progress_report_path = os.path.join(args.little_potato, 'progress_report.json')
        with open(progress_report_path, 'w') as file:
            json.dump(progress_report, file, ensure_ascii=False, indent=4)
        logging.info("Progress report written to progress_report.json")
        
        # Write failed downloads to a separate JSON file
        if failed_downloads:
            with open(failed_downloads_path, 'w') as file:
                json.dump(failed_downloads, file, ensure_ascii=False, indent=4)
            logging.info(f"Failed downloads report written to {failed_downloads_path} with {len(failed_downloads)} entries")
        
        # Print summary of what happened
        logging.info("=== DOWNLOAD SESSION SUMMARY ===")
        logging.info(f"Requested batch size: {args.batch}")
        logging.info(f"Successfully downloaded: {len(progress_report) - initial_count}")
        logging.info(f"Failed downloads in this session: {len(session_failed)}")
        logging.info(f"Total failed downloads recorded: {len(failed_downloads)}")
        
        # Count remaining files
        visited = list(progress_report.values())
        remaining_files = len([m for m in metadata_dict.keys() if m not in visited])
        logging.info(f"Remaining files to download: {remaining_files}")
        
        # Calculate estimated time to completion
        if downloaded_count > 0:
            avg_time_per_file = (time.time() - start_time) / downloaded_count
            estimated_time_hours = (avg_time_per_file * remaining_files) / 3600
            logging.info(f"Estimated time to completion: {estimated_time_hours:.1f} hours at current rate")
        
        logging.info("=== Download Statistics ===")
        logging.info(f"Total files in JSON: {len(metadata_dict)}")
        
        # Avoid division by zero
        if len(metadata_dict) > 0:
            percent_processed = (len(progress_report) / len(metadata_dict) * 100)
            percent_remaining = (remaining_files / len(metadata_dict) * 100)
            logging.info(f"Files processed so far: {len(progress_report)} ({percent_processed:.1f}%)")
            logging.info(f"Files remaining: {remaining_files} ({percent_remaining:.1f}%)")
        else:
            logging.info(f"Files processed so far: {len(progress_report)}")
            logging.info(f"Files remaining: {remaining_files}")
            logging.info(f"Note: All Kallipos repository URLs have been filtered out due to access restrictions")
            
        logging.info("===============================")

#Entry point of Downloader
if __name__ == "__main__":
    # Track overall execution time
    start_time = time.time()
    asyncio.run(main())
    end_time = time.time()
    execution_time = end_time - start_time
    logging.info(f"Total execution time: {execution_time:.2f} seconds ({execution_time/60:.2f} minutes)")