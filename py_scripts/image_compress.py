from statistics import quantiles
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

def get_save_path(file_path, num):
    parent_name, parent_dir = get_image_parent_dir(file_path)
    save_dir = parent_dir + "\\" + parent_name + "_compress"
    if not os.path.exists(save_dir):
        os.mkdir(save_dir)

    return save_dir + "\\" + str(num) + file_path[-4:]

def convert_png_to_jpg(file_path, num):
    if file_path.endswith(".png"):
        image = Image.open(file_path).convert('RGB')
        save_path = get_save_path(file_path[:-4] + ".jpg", num)
        image.save(save_path)
        return True, save_path
    else:
        return False, file_path

def compress_one_file_internal(file_path, num):

    result, converted_path = convert_png_to_jpg(file_path, num)

    if result:
        save_path = converted_path
    else:
        save_path = get_save_path(converted_path, num)

    if os.stat(converted_path).st_size <= 1024*1024:
        
        if file_path.endswith(".png"):
            return

        copy2(converted_path, save_path)
        return

    image = Image.open(converted_path)
    #image = image.resize((int(image.width/3), int(image.height/3)), Image.ANTIALIAS)
    image.save(save_path, optimize=True)

    if os.stat(save_path).st_size > 1024*1024:
        image.save(save_path, optimize=True, quality=40)

    assert(os.stat(save_path).st_size < 1024*1024)

def compress_one_file(file_path, num):

    if not file_path.endswith(".jpg") and \
        not file_path.endswith(".png"):
        return

    compress_one_file_internal(file_path, num)

def main(argv):
    traverse_dir_files.traverse(argv[0], compress_one_file)

def usage():
    print("\nusage: python image_compress.py image_dir\n\n"
          "eg:\n"
          "  python image_compress.py "
          "D:\\BaiduNetdiskDownload\\galgame_cg\\生命のスペア I was born for you \n\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        usage()
        sys.exit(0)
    main(sys.argv[1:])
