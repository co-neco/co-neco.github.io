import sys, os

def write_file(file_path, content):
    f = open(file_path, "wb")
    f.write(bytes(content, 'utf-8'))
    f.close()

def get_cur_python_file_path():
    return os.path.realpath(__file__)

def output_image_urls(image_dir, host_image_dir_name):

    host_dir_root = "https://gitee.com/co-neco/pic_bed/raw/master"
    image_url_str = ""
    image_url_index = 0

    image_dir_walk = os.walk(image_dir)
    for root, directories, files in image_dir_walk:
        for file in files:
            if not file.endswith(".jpg") and \
            not file.endswith(".png"):
                continue

            image_url_str += host_dir_root + "/" + host_image_dir_name + "/" + file + "\r\n"
            image_url_index += 1

    write_file(
        os.path.abspath(get_cur_python_file_path() + "\\..\\..\\source\\_data\\image_host\\" + host_image_dir_name + ".txt"), 
        image_url_str)

def main(argv):
    image_dir = argv[0]
    host_image_dir_name = argv[1]

    output_image_urls(image_dir, host_image_dir_name)

def usage():
    print("\nusage: python write_image_urls_to_host.py image_dir host_image_dir_name\n\n"
          "eg:\n"
          "  python write_image_urls_to_host.py D:\\BaiduNetdiskDownload\\galgame_cg\\生命のスペア I was born for you \n\n"
          "  inochi\n\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        usage()
        sys.exit(0)
    main(sys.argv[1:])