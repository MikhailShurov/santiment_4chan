import asyncio
import datetime
import html
import json
import os
import re
import time

import aiofiles
import aiohttp

ARCHIVE = 'https://a.4cdn.org/biz/archive.json'
CATALOG = 'https://a.4cdn.org/biz/catalog.json'
TASKS_AMOUNT = 3
lock = asyncio.Lock()


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
    return datetime.datetime.fromtimestamp(int(dt)).strftime('%a, %d %b %Y %H:%M:%S') + " GMT"


# if no "com" key, return "" instead of None
def get_text(source: dict) -> str:
    return cleanhtml(source.get("com", ""))


async def async_file_writer(file_name: str, lines: str):
    async with lock:
        async with aiofiles.open(file_name, mode='w') as f:
            await f.write(lines)


async def set_catalog_mod_date():
    async with lock:
        with open("config.json", "r") as file:
            config = json.load(file)
        config["catalog_modified_date"] = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S') + " GMT"
        with open("config.json", "w") as file:
            json.dump(config, file)


async def set_archive_mod_date():
    async with lock:
        with open("config.json", "r") as file:
            config = json.load(file)
        config["archive_modified_date"] = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S') + " GMT"
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


async def create_file(no: int, directory: str) -> None:
    """
    Creates a file with title, text and link on image of thread and comments with text and image link
    :param no: index of thread (["no"] parameter in API)
    :param directory: directory where to save file
    :return: nothing
    """
    link = fr"https://boards.4channel.org/biz/thread/{no}.json"
    async with aiohttp.ClientSession() as session:
        async with session.get(link) as response:
            reply = await response.json()
            context = {
                "title": get_title(reply["posts"][0]),
                "text": get_text(reply["posts"][0]),
                "date": get_date(reply["posts"][0]),
                "img_link": get_image_link(reply["posts"][0]),
                "replies": get_replies(reply["posts"])
            }
            file_path = os.path.join(directory, f"{no}.json")
            await async_file_writer(file_path, json.dumps(context))
            # with open(file_path, "w") as file:
            #     json.dump(context, file)


async def change_comments(no: int, path: str, last_modified: str) -> None:
    """
    Adding new comments to file if new where added
    :param last_modified: date of last time modified, example: Wed, 21 Dec 2022 16:40:00 GMT
    :param no: index of thread
    :param path: directory where file is located
    :return: nothing
    """
    path = os.path.join(path, f"{no}.json")
    async with aiofiles.open(path, mode='r') as file:
        contents = await file.read()
        thread = json.loads(contents)
    if last_modified:
        last_modified += " GMT"
    headers = {"If-Modified-Since": last_modified}
    comments = thread["replies"]
    link = fr"https://boards.4channel.org/biz/thread/{no}.json"
    async with aiohttp.ClientSession() as session:
        async with session.get(link) as reply:  # headers=headers
            if not reply or reply.status == 304:
                return
            reply = await reply.json()
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
                # with open(path, "w") as file:
                #     json.dump(thread, file)


async def analyze_pages(reply: list, directory: str, last_modified: str) -> None:
    for page in reply:
        for thread in page["threads"]:
            # start = time.time()
            no = thread["no"]
            path = os.path.join(directory, f"{no}.json")
            if os.path.exists(path):
                await change_comments(no, directory, last_modified)
            else:
                await create_file(no, directory)
            # sleep = 1 - (time.time() - start) if (1 - (time.time() - start)) > 0 else 0
            # time.sleep(sleep)


async def check_catalog() -> None:
    """
    :return: updates files from catalog
    """
    async with lock:
        with open("config.json", "r") as file:
            config = json.load(file)
    directory = config["folder_path"]
    last_modified = config["catalog_modified_date"]
    await set_catalog_mod_date()
    async with aiohttp.ClientSession() as session:
        async with session.get(CATALOG) as response:
            reply = await response.json()
            tasks = []
            for i in range(0, len(reply), TASKS_AMOUNT):
                pages = reply[i:min(i + TASKS_AMOUNT, len(reply))]
                tasks.append(asyncio.create_task(analyze_pages(pages, directory, last_modified)))
            await asyncio.gather(*tasks)


async def analyze_archive(ids: list, directory: str, last_modified: str) -> None:
    # start = time.time()
    for no in ids:
        if os.path.exists(os.path.join(directory, f"{no}.json")):
            await change_comments(no, directory, last_modified)
        else:
            await create_file(no, directory)
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
            last_local_thread_index = reply.index(last_local_thread)
            unmarked_ids = len(reply) - 1 - last_local_thread_index

            for i in range(last_local_thread_index + 1, len(reply), unmarked_ids // TASKS_AMOUNT + 1):
                ids = reply[i:min(i + unmarked_ids // TASKS_AMOUNT + 1, len(reply))]
                tasks.append(asyncio.create_task(analyze_archive(ids, config["folder_path"], last_modified)))
            await asyncio.gather(*tasks)

            config["last_archive_element"] = reply[-1]
            # async with lock:
            #     with open("config.json", "w") as file:
            #         json.dump(config, file)
            #     print("config successfully updated!")


def time_it(func):
    async def wrapper(*args, **kwargs):
        start = time.time()
        await func(*args, **kwargs)
        end = time.time()
        print('Ellapsed async time: {}'.format(end - start))

    return wrapper


@time_it
async def main():
    try:
        with open("config.json", "r") as file:
            directory = json.load(file)["folder_path"]
        if not os.path.exists(directory):
            os.mkdir(directory)
    except:
        print("Problems with given directory")
    try:
        await check_catalog()
        await archive_rec()
    except Exception as e:
        pass
