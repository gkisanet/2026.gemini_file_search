import os
import datetime

def get_file_times(filepath):
    stat = os.stat(filepath)
    # create time
    ctime = datetime.datetime.fromtimestamp(stat.st_ctime)
    # modified time
    mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
    print(f"File system ctime: {ctime}")
    print(f"File system mtime: {mtime}")

get_file_times('README.md')
