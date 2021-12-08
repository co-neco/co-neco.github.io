import re
import os
import sys
import requests


def parse_img_urls(web_content):
    pattern = "//i0.hdslb.com/bfs/article/[0-9a-f]*\.jpg"
    img_url_list = re.findall(pattern, web_content)
    assert (len(img_url_list) != 0)
    return img_url_list


def read_file(file_path):
    f = open(file_path, "rb")
    content = f.read().decode('utf-8')
    f.close()
    return content


def save_imgs(img_url_list, save_root_dir):

    if not os.path.exists(save_root_dir):
        os.makedirs(save_root_dir)

    for img_url in img_url_list:
        save_path = save_root_dir + "\\" + os.path.split(img_url)[1]
        
        try:
            if not os.path.exists(save_path):
                request = requests.get("https:" + img_url)
                with open(save_path, "wb") as f:
                    f.write(request.content)
        except Exception as url:
            print(url)


def main(argv):
    web_content = read_file(argv[0])
    img_url_list = parse_img_urls(web_content)
    save_imgs(img_url_list, argv[1])


def usage():
    print("\nusage: python parse_bilibili_imgs.py web_cotent_file_path save_path\n\n"
          "eg:\n"
          "  python parse_bilibili_imgs.py E\\tmp\\bilibili_saenai_cg_2.txt E:\\github\\coneco\\source\\_data\\image_host\\honoguraki\n\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        usage()
        sys.exit(0)
    main(sys.argv[1:])
