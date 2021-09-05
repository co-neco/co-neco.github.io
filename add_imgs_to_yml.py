import sys
import os


def get_current_dir():
    return os.path.dirname(os.path.realpath(__file__))


def add_imgs_to_yml_file(image_dir, image_yml_file_path):
    path = os.walk(image_dir)

    image_yml_file = open(image_yml_file_path, "ab")

    image_yml_file.write(bytes("\r\n", 'utf-8'))
    for root, directories, files in path:
        for file in files:
            image_yml_file.write(bytes("- https://conecoy.cn/images/" + file + "\r\n", 'utf-8'))

    image_yml_file.close()


def main():
    root_dir = get_current_dir()
    image_dir = root_dir + "\\source\\_data\\images"
    image_yml_file_path = root_dir + "\\themes\\shoka\\_images.yml"

    add_imgs_to_yml_file(image_dir, image_yml_file_path)

if __name__ == "__main__":
    main()
