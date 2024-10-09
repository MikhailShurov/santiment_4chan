import asyncio
import os
import shutil

import schedule
import time

from fixed_functions import main as async_main
from functions import main as sync_main


if __name__ == "__main__":
    asyncio.run(async_main())
    print('async main finished work')
    shutil.rmtree('threads')
    if not os.path.exists('threads'):
        print('threads deleted, started sync version')
    sync_main()
    print('sync main finished work')
    schedule.every().hour.do(sync_main)
    while True:
        schedule.run_pending()
        time.sleep(1)
