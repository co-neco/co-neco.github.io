import sys

def output_image_urls(image_dir, image_format, image_total_num):

    root = "https://gitee.com/co-neco/pic_bed/raw/master"


    for i in range(0, image_total_num):
        print(root + "/" + image_dir + "/" + str(i) + "." + image_format)

def main(argv):
    image_dir = argv[0]
    image_format = argv[1]
    image_total_num = int(argv[2])

    output_image_urls(image_dir, image_format, image_total_num)

def usage():
    print("\nusage: python output_image_urls.py image_dir image_format image_totoal_num\n\n"
          "eg:\n"
          "  python image_compress.py inochi png 17\n\n")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        usage()
        sys.exit(0)
    main(sys.argv[1:])