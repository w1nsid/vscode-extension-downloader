import asyncio
import json
import os
import random

import aiohttp
import pyppeteer
from bs4 import BeautifulSoup
from semver import compare as compare_versions

with open('header.json', 'r') as file:
    HEADERS = json.load(file)


def parse_dir(directory):
    print('parse by directory: ', directory)
    extensions = []

    try:
        files = [f for f in os.listdir(directory) if f.endswith('.vsix')]
        for extension in files:
            last_index_of_dash = extension.rfind('-')
            last_index_of_dot = extension.rfind('.')
            first_index_of_dot = extension.find('.')

            app = extension[:last_index_of_dash]
            publisher = extension[:first_index_of_dot]
            name = app.split('.')
            version = extension[last_index_of_dash + 1:last_index_of_dot]

            extensions.append({'app': app, 'publisher': publisher, 'name': name[1], 'version': version})
    except Exception as err:
        print(err)

    return extensions


def parse_file(directory='.'):
    print('parse by file')
    print('parsing directory: ', directory)
    extensions = []

    try:
        with open(f'{directory}/extensions.txt', 'r') as file:
            lines = file.readlines()

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                app = line.split('@', 1)
                publisher = app[0].split('.')

                extensions.append({'app': app[0], 'publisher': publisher[0], 'name': publisher[1], 'version': app[1]})
    except Exception as err:
        print(err)
        print('Ensure extensions.txt exists in the root directory')

    return extensions


async def crawl_with_puppeteer(url):
    browser = await pyppeteer.launch()
    page = await browser.newPage()
    await page.goto(url)
    content = await page.content()
    await browser.close()
    return content


async def fetch_content_with_aiohttp(url, retries=3):
    for attempt in range(retries):
        try:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.text()
                    print(f"Attempt {attempt + 1} failed with status {response.status}. Retrying...")
        except Exception as e:
            print(f"Retry attempt {attempt + 1} due to error: {e}")
    print(f"Failed to fetch content from {url} after {retries} retries.")
    return None


async def get_extension_version(url):
    for attempt in range(3):
        try:
            response = await crawl_with_puppeteer(url)
            soup = BeautifulSoup(response, 'html.parser')
            info_table = soup.select('.ux-table-metadata > tbody > tr > td')[1]
            version = info_table.get_text().strip()
            return version
        except Exception as e:
            if attempt > 0:
                print(f"Retry attempt {attempt + 1} due to error: {e}")
            await asyncio.sleep(1)
            continue
    print(f"Failed to fetch version from {url} after 3 retries.")
    return None


async def start_download(extension, url, directory, last_ver=None, max_retries=5):
    """
    Downloads the extension file from the provided URL.

    Usage:

    >>> await start_download({'app': 'YourExtensionName'}, 'http://example.com/download', '/path/to/save')
    
    Args:
    - extension (dict): Dictionary containing 'app' key for the name of the extension.
    - url (str): URL to download from.
    - directory (str): Directory to save the downloaded file.
    - last_ver (str, optional): Last version of the extension. Defaults to None.
    - max_retries (int, optional): Max retries in case of rate limiting. Defaults to 5.
    
    Returns:
    Status of the download. True if successful, False otherwise.
    """

    retry_after = 1  # Default delay in seconds if Retry-After header is not found
    status = False

    print(f"Downloading {extension['app']}...")
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                print(f"Retry attempt {attempt + 1}...")

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=HEADERS) as response:
                    if response.status == 429:  # Rate limited
                        retry_after = int(response.headers.get('Retry-After', retry_after))
                        jitter = random.uniform(0, 0.5)  # Adding a jitter factor
                        sleep_duration = retry_after + jitter
                        print(f"Rate limited. Retrying in {sleep_duration:.2f} seconds...")
                        await asyncio.sleep(sleep_duration)
                        continue

                    elif response.status == 200:
                        if response.content_disposition and response.content_disposition.filename:
                            filename = response.content_disposition.filename
                        else:
                            filename = f"{extension['app']}-{last_ver}.vsix"

                        if "@" in filename and "win32-x64" not in filename.lower():
                            url += "?targetPlatform=win32-x64"
                            continue  # Retry immediately with the modified URL

                        content = await response.read()
                        with open(os.path.join(directory, filename), 'wb') as f:
                            f.write(content)
                        print(f"{filename} downloaded.")
                        status = True
                        break  # Successfully downloaded

                    else:
                        print(f"Unable to download {url}. Status: {response.status}")
                        break  # Stop on unexpected error

        except Exception as e:
            print(f"Error while downloading {url}: {e}")
            break

    return status


def delete_extensions(old_extensions, directory):
    for ext in old_extensions:
        file_path = os.path.join(directory, f"{ext['app']}-{ext['version']}.vsix")
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"{ext['app']}-{ext['version']}.vsix deleted")
            except Exception as e:
                print(f"Error while deleting {file_path}: {e}")


def get_extensions(mode, directory):
    if mode == 'dir':
        return parse_dir(directory)
    return parse_file(directory)


async def start(mode, update, directory):
    old_extensions = []
    failed_extensions = []
    extensions = get_extensions(mode, directory)

    await process_ext(directory, old_extensions, failed_extensions, extensions, update)

    delete_extensions(old_extensions, directory)

    if failed_extensions:
        print("Retry failed downloads? (y/n)")
        retry = input().strip().lower()
        if retry == 'y':
            failed_extensions_2 = []
            old_extensions_2 = []
            await process_ext(directory, old_extensions_2, failed_extensions_2, failed_extensions)


async def process_ext(directory, old_extensions, failed_extensions, extensions, update=False):
    for ext in extensions:
        desired_version = ext['version']
        if update:
            latest_version = await get_extension_version(
                f"https://marketplace.visualstudio.com/items?itemName={ext['app']}"
            )
            # print(f"{ext}, latest version: {latest_version}")

            if not latest_version:
                print(f"Unable to fetch latest version for {ext['app']}. Skipping...")
                failed_extensions.append(ext)
                continue

            if compare_versions(latest_version, ext['version']) > 0:
                print(f"New version found for {ext['app']}")
                old_extensions.append(ext)

            desired_version = latest_version

        file_exists = os.path.exists(os.path.join(directory, f"{ext['app']}-{desired_version}.vsix"))
        if file_exists:
            print(f"{ext['app']}-{desired_version}.vsix already exists. Skipping...")
            continue

        url = f"https://marketplace.visualstudio.com/_apis/public/gallery/publishers/{ext['publisher']}/vsextensions/{ext['name']}/{desired_version}/vspackage"
        result = await start_download(ext, url, directory, desired_version)
        if not result:
            failed_extensions.append(ext)


# async def handle_extension(ext, directory):
#     latest_version = await get_extension_version(f"https://marketplace.visualstudio.com/items?itemName={ext['app']}")
#     is_new = True
#     succes = False

#     if not latest_version:
#         print(f"Unable to fetch latest version for {ext['app']}. Skipping...")
#         return is_new, succes

#     if compare_versions(latest_version, ext['version']) > 0:
#         print(f"New version found for {ext['app']}")
#         is_new = False

#     file_exists = os.path.exists(os.path.join(directory, f"{ext['app']}-{latest_version}.vsix"))
#     if file_exists:
#         print(f"{ext['app']}-{latest_version}.vsix already exists and up to date. Skipping...")
#         succes = True
#         return is_new, succes

#     url = f"https://marketplace.visualstudio.com/_apis/public/gallery/publishers/{ext['publisher']}/vsextensions/{ext['name']}/{latest_version}/vspackage"
#     succes = await start_download(ext, url, directory, latest_version)
#     return is_new, succes

# async def start_multi(mode, directory):

#     extensions = get_extensions(mode, directory)

#     # Run tasks concurrently
#     results = await asyncio.gather(*[handle_extension(ext, directory) for ext in extensions])

#     # Filter extensions based on results
#     old_extensions = [extensions[i] for i, (is_new, _) in enumerate(results) if not is_new]
#     up_to_date_extensions = [extensions[i] for i, (is_new, success) in enumerate(results) if is_new and success]
#     failed_extensions = [extensions[i] for i, (_, success) in enumerate(results) if not success]

#     # Delete old extensions
#     delete_extensions(old_extensions, directory)

#     # Offer to retry failed downloads
#     if failed_extensions:
#         print("Retry failed downloads? (y/n)")
#         retry = input().strip().lower()
#         if retry == 'y':
#             await asyncio.gather(*[handle_extension(ext, directory) for ext in failed_extensions])

#     # Log successful updates
#     if up_to_date_extensions:
#         print("The following extensions are up-to-date:")
#         for ext in up_to_date_extensions:
#             print(f"{ext['app']} v{ext['version']}")

directory = "mynewprofile"
scan_mode = 'file'
update = False
asyncio.run(start(scan_mode, update, directory))
