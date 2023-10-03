import asyncio
import os

import aiohttp
import pyppeteer
from bs4 import BeautifulSoup
from semver import compare as compare_versions

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0'}


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


async def get_extension_version(url):
    try:
        response = await crawl_with_puppeteer(url)
        soup = BeautifulSoup(response, 'html.parser')
        info_table = soup.select('.ux-table-metadata > tbody > tr > td')[1]
        version = info_table.get_text().strip()
        return version
    except Exception as e:
        print(f"Unable to fetch extension version at {url}: {e}")
        return None


async def start_download(extension, url, directory):
    try:
        print(f"Starting download from {url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=HEADERS) as response:
                if response.status == 200:
                    content = await response.read()
                    with open(os.path.join(directory, f"{extension['app']}-{extension['version']}.vsix"), 'wb') as f:
                        f.write(content)
                else:
                    print(f"Unable to download {extension}. Status: {response.status}")
    except Exception as e:
        print(f"Error while downloading {extension}: {e}")


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


async def start(mode, directory):
    old_extensions = []
    extensions = get_extensions(mode, directory)

    for ext in extensions:
        latest_version = await get_extension_version(
            f"https://marketplace.visualstudio.com/items?itemName={ext['app']}"
        )
        print(f"{ext}, latest version: {latest_version}")

        if not latest_version:
            continue

        file_exists = os.path.exists(os.path.join(directory, f"{ext['app']}-{latest_version}.vsix"))
        if file_exists:
            continue

        url = f"https://marketplace.visualstudio.com/_apis/public/gallery/publishers/{ext['publisher']}/vsextensions/{ext['name']}/{latest_version}/vspackage"
        await start_download(ext, url, directory)

        if compare_versions(latest_version, ext['version']) > 0:
            old_extensions.append(ext)

    delete_extensions(old_extensions, directory)


directory = "ext"
mode = 'file'
asyncio.run(start(mode, directory))
