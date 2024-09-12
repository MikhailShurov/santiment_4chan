# 4chan_scraper

Entrypoing: main.py
Files config.json, main.py and functions.py should be in the same directory.

- In config.json file:
  - Set `folder_path` variable to directory, where saved threads will be stored
  - To run parsing from scratch set `last_archive_element` to 0, `archive_modified_date` and catalog_modified_date to `''` (empty string)
 
- Script save threads to separate files. File structure:
  - "title" - thread's title (empty string, if no title)
  - "text" - thread's text (empty string, if no text)
  - "img_link" - link to image in thread (empty string, if no image)
  - "replies" - list of comment to thread (empty, if no comments). Comment entity structure:
    - "text" - comment's text (empty string, if no text)
    - "img_link" - link to image in comment (empty string, if no image)

Update period is 1 hour. First run could be a little big longer cause of archive size (next run will be after 1 hour after the end of update).
