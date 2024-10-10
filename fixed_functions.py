import asyncio
from datetime import datetime
import html
import json
import os
import re
import time
from enum import Enum

import aiofiles
import aiohttp
from aiohttp import ContentTypeError

from logger import log_message, log_error

ARCHIVE = 'https://a.4cdn.org/biz/archive.json'
CATALOG = 'https://a.4cdn.org/biz/catalog.json'
CATALOG_MODIFIED = 'https://a.4cdn.org/biz/threads.json'
TASKS_AMOUNT = 4
lock = asyncio.Lock()


class Location(Enum):
    CATALOG = "CATALOG"
    ARCHIVE = "ARCHIVE"


# cleanhtml version but without loops, complexity = O(n), n = len(html_s)
def cleanhtml(raw_html: str) -> str:
    """
    :param raw_html: html code
    :return: text without html code and symbols
    """
    clean_a_tags = re.sub(r'<a[^>]*>.*?</a>', '', raw_html, flags=re.DOTALL)
    # clean_a_tags = clean_a_tags.replace('<br>', '\n')  # enable if u want same structure as on the forum
    return html.unescape(re.sub(r'<[^>]+>', '', clean_a_tags))


def get_image_link(source: dict) -> str:
    ext = source.get("ext")
    i_name = source.get("tim")
    if ext and i_name:
        return f"https://i.4cdn.org/biz/{i_name}{ext}"
    return ""


def get_title(source: dict) -> str:
    return source.get("sub", "")


def get_date(source: dict) -> str:
    dt = source.get("time", "")
    return datetime.fromtimestamp(int(dt)).strftime('%a, %d %b %Y %H:%M:%S') + " GMT"


# if no "com" key, return "" instead of None
def get_text(source: dict) -> str:
    return cleanhtml(source.get("com", ""))


async def async_file_writer(file_name: str, lines: str):
    async with aiofiles.open(file_name, mode='w') as f:
        await f.write(lines)


async def set_catalog_mod_date():
    async with lock:
        with open("config.json", "r") as file:
            config = json.load(file)
        config["catalog_modified_date"] = datetime.now().strftime('%a, %d %b %Y %H:%M:%S') + " GMT"
        with open("config.json", "w") as file:
            json.dump(config, file)


async def set_archive_mod_date():
    async with lock:
        with open("config.json", "r") as file:
            config = json.load(file)
        config["archive_modified_date"] = datetime.now().strftime('%a, %d %b %Y %H:%M:%S') + " GMT"
        with open("config.json", "w") as file:
            json.dump(config, file)


def get_replies(source: list) -> list:
    replies = []
    if "replies" in source[0]:
        for i in source[1:]:
            comment = {
                "text": get_text(i),
                "date": get_date(i),
                "img_link": get_image_link(i)
            }
            replies.append(comment)
    return replies


async def create_file(no: int, directory: str, location: Location) -> None:
    """
    Creates a file with title, text and link on image of thread and comments with text and image link
    :param no: index of thread (["no"] parameter in API)
    :param directory: directory where to save file
    :param location: used in logger to determine what object is being worked on
    :return: nothing
    """
    link = fr"https://boards.4channel.org/biz/thread/{no}.json"
    async with aiohttp.ClientSession() as session:
        async with session.get(link) as response:
            try:
                reply = await response.json()
            except ContentTypeError as _:
                log_error(f"Unable to parse JSON from {link}")
                return
            context = {
                "title": get_title(reply["posts"][0]),
                "text": get_text(reply["posts"][0]),
                "date": get_date(reply["posts"][0]),
                "img_link": get_image_link(reply["posts"][0]),
                "replies": get_replies(reply["posts"])
            }
            file_path = os.path.join(directory, f"{no}.json")
            await async_file_writer(file_path, json.dumps(context))
            log_message(f"{location.value} | SAVED NEW THREAD | {no}.json")
            # with open(file_path, "w") as file:
            #     json.dump(context, file)


async def change_comments(no: int, path: str, last_modified: str, location: Location) -> None:
    """
    Adding new comments to file if new where added
    :param last_modified: date of last time modified, example: Wed, 21 Dec 2022 16:40:00 GMT
    :param no: index of thread
    :param path: directory where file is located
    :param location: used in logger to determine what object is being worked on
    :return: nothing
    """
    path = os.path.join(path, f"{no}.json")
    async with aiofiles.open(path, mode='r') as file:
        contents = await file.read()
        thread = json.loads(contents)
    if last_modified:
        last_modified += " GMT"

    comments = thread["replies"]
    link = fr"https://boards.4channel.org/biz/thread/{no}.json"
    async with aiohttp.ClientSession() as session:
        async with session.get(link) as reply:
            try:
                reply = await reply.json()
            except ContentTypeError as _:
                log_error(f"Unable to parse JSON from {link}")
                return
            reply = reply["posts"][1:]
            local_rep = len(comments)
            real_rep = len(reply)
            if real_rep > local_rep:
                for i in reply[local_rep:]:
                    comment = {
                        "text": get_text(i),
                        "date": get_date(i),
                        "img": get_image_link(i)
                    }
                    comments.append(comment)
                thread["replies"] = comments
                await async_file_writer(path, json.dumps(thread))
                log_message(f"{location.value} | THREAD UPDATED | {no}.json")


async def analyze_pages(reply: list, directory: str, last_modified: str, catalog_last_mod: int,
                        threads_mod_date: dict = None) -> None:
    for page in reply:
        for thread in page["threads"]:
            # start = time.time()
            no = thread["no"]
            # Тут была проблема, что если тред не был изменен, скрапер все равно делал запрос, чтобы убедиться в этом
            path = os.path.join(directory, f"{no}.json")
            if threads_mod_date:
                seconds_since_thread_changed = threads_mod_date[no] - catalog_last_mod
                if seconds_since_thread_changed > 0:
                    if os.path.exists(path):
                        await change_comments(no, directory, last_modified, Location.CATALOG)
                    else:
                        await create_file(no, directory, Location.CATALOG)
            # sleep = 1 - (time.time() - start) if (1 - (time.time() - start)) > 0 else 0
            # time.sleep(sleep)


async def extract_threads_mod_time(pages: list) -> dict:
    result = {}
    for page in pages:
        for thread in page['threads']:
            result[thread["no"]] = thread["last_modified"]
    return result


async def check_catalog() -> None:
    """
    :return: updates files from catalog
    """
    async with lock:
        with open("config.json", "r") as file:
            config = json.load(file)
    directory = config["folder_path"]
    last_modified = config["catalog_modified_date"]
    dt = datetime.strptime(last_modified, "%a, %d %b %Y %H:%M:%S %Z")
    catalog_mod_timestamp = int(dt.timestamp())

    await set_catalog_mod_date()
    async with aiohttp.ClientSession() as session:

        async with session.get(CATALOG_MODIFIED) as response:
            json_data = await response.json()
            tasks = []
            for i in range(0, len(json_data), len(json_data) // TASKS_AMOUNT + 1):
                pages = json_data[i:min(i + len(json_data) // TASKS_AMOUNT + 1, len(json_data))]
                tasks.append(asyncio.create_task(extract_threads_mod_time(pages)))
            results = await asyncio.gather(*tasks)
            threads_mod_date = {}
            for result in results:
                threads_mod_date.update(result)

        async with session.get(CATALOG) as response:
            reply = await response.json()
            tasks = []
            for i in range(0, len(reply), len(reply) // TASKS_AMOUNT + 1):
                pages = reply[i:min(i + len(reply) // TASKS_AMOUNT + 1, len(reply))]
                tasks.append(asyncio.create_task(analyze_pages(pages, directory, last_modified, catalog_mod_timestamp,
                                                               threads_mod_date)))
            await asyncio.gather(*tasks)


async def analyze_archive(ids: list, directory: str, last_modified: str) -> None:
    # start = time.time()
    for no in ids:
        if os.path.exists(os.path.join(directory, f"{no}.json")):
            await change_comments(no, directory, last_modified, Location.ARCHIVE)
        else:
            await create_file(no, directory, Location.ARCHIVE)
        # sleep = 1 - (time.time() - start) if (1 - (time.time() - start)) > 0 else 0
        # time.sleep(sleep + 0.01)


async def archive_rec() -> None:
    """
    Updating archived threads
    :return: nothing
    """
    async with lock:
        with open("config.json", "r") as file:
            config = json.load(file)
    last_local_thread = config["last_archive_element"]
    last_modified = config["archive_modified_date"]
    await set_archive_mod_date()
    async with aiohttp.ClientSession() as session:
        async with session.get(ARCHIVE) as response:
            reply = await response.json()

            tasks = []
            if last_local_thread not in reply:
                last_local_thread = reply[0]
            last_local_thread_index = reply.index(last_local_thread)
            unmarked_ids = len(reply) - 1 - last_local_thread_index

            for i in range(last_local_thread_index + 1, len(reply), unmarked_ids // TASKS_AMOUNT + 1):
                ids = reply[i:min(i + unmarked_ids // TASKS_AMOUNT + 1, len(reply))]
                tasks.append(asyncio.create_task(analyze_archive(ids, config["folder_path"], last_modified)))
            await asyncio.gather(*tasks)

            config["last_archive_element"] = reply[-1]
            async with lock:
                with open("config.json", "w") as file:
                    json.dump(config, file)


def time_it(func):
    async def wrapper(*args, **kwargs):
        start = time.time()
        await func(*args, **kwargs)
        end = time.time()
        log_message('Ellapsed time of async version code: {}'.format(end - start))
    return wrapper


@time_it
async def main():
    try:
        with open("config.json", "r") as file:
            directory = json.load(file)["folder_path"]
        if not os.path.exists(directory):
            os.mkdir(directory)
    except Exception as _:  # NOQA
        log_error("Problems with given directory")
    try:
        await check_catalog()
        await archive_rec()
    except Exception as e:  # NOQA
        log_error(e)
        pass
