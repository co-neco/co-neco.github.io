import sys, os
import traverse_dir_files
from shutil import copy2

from PIL import Image

def get_image_parent_dir(image_path):

    parent_name = ""
    parent_dir = ""

    try:
        index = image_path.rindex("\\")
        parent_index = image_path[:index-1].rindex("\\")
        parent_name = image_path[parent_index+1:index]
        parent_dir = image_path[:parent_index]
    except ValueError:
        print("image path error!!!!!!")

    return parent_name, parent_dir

def compress_one_file_internal(file_path, save_path):

    if os.stat(file_path).st_size < 1024*1024:
        copy2(file_path, save_path)
        return

    image = Image.open(file_path)
    image = image.resize((int(image.width/2), int(image.height/2)), Image.ANTIALIAS)

    image.save(save_path, optimize=True, quality=50)

def compress_one_file(file_path, num):

    if not file_path.endswith(".jpg") and \
        not file_path.endswith(".png"):
        return

    parent_name, parent_dir = get_image_parent_dir(file_path)
    save_dir = parent_dir + "\\" + parent_name + "_compress"
    if not os.path.exists(save_dir):
        os.mkdir(save_dir)

    save_path = save_dir + "\\" + str(num) + file_path[-4:]

    compress_one_file_internal(file_path, save_path)

def main(argv):
    traverse_dir_files.traverse(argv[0], compress_one_file)

def usage():
    print("\nusage: python image_compress.py image_dir image_prefix\n\n"
          "eg:\n"
          "  python image_compress.py "
          "D:\\BaiduNetdiskDownload\\galgame_cg\\生命のスペア I was born for you \n\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        usage()
        sys.exit(0)
    main(sys.argv[1:])
