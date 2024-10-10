import asyncio
import os
import shutil

import schedule
import time

from fixed_functions import main as async_main
from functions import main as sync_main
from logger import log_message


def scrape_async():
    asyncio.run(async_main())


if __name__ == "__main__":
    try:
        print('Async version ARCHIVE threads collecting:')
        scrape_async()
        # sync version of scraper
        if os.path.exists('threads'):
            shutil.rmtree('threads')
        print('Sync version ARCHIVE threads collecting:')
        sync_main()
        # schedule.every().hour.do(sync_main)
        # schedule.every().hour.do(scrape_async)
        # while True:
        #     schedule.run_pending()
        #     time.sleep(1)
    except KeyboardInterrupt:
        log_message("TERMINATED")
