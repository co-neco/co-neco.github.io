import sys, os
import traverse_dir_files
from shutil import copy2

save_dir = ""

def copy_one_file(file_path, num):

    global save_dir

    if not os.path.exists(save_dir):
        os.mkdir(save_dir)

    if not file_path.endswith(".jpg") and \
        not file_path.endswith(".png"):
        return

    new_file_path = save_dir + "\\" +  str(num) + file_path[-4:]

    copy2(file_path, new_file_path)

def main(argv):
    global save_dir
    save_dir = argv[1]
    traverse_dir_files.traverse(argv[0], copy_one_file)

def usage():
    print("\nusage: python rename_images.py image_src_dir image_dest_dir image_prefix\n\n"
          "eg:\n"
          "  python rename_images.py "
          "D:\\BaiduNetdiskDownload\\galgame_cg\\生命のスペア I was born for you_compress "
          "E:\\github\\coneco\\source\\_data\\image_host\\inochi \n\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        usage()
        sys.exit(0)
    main(sys.argv[1:])
