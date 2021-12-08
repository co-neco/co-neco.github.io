import os

def traverse(dir, callback):

    file_num = 0

    with os.scandir(dir) as dirEntry:
        for entry in dirEntry:
            if os.path.isdir(entry.path):
                traverse(entry.path)

            assert(os.path.isfile(entry.path))
            
            callback(entry.path, file_num)

            file_num = file_num + 1