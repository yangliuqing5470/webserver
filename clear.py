import os
import shutil


def main():
    for item in os.listdir(os.getcwd()):
        path = os.path.join(os.getcwd(), item)
        if item == "app.log" and os.path.isfile(path):
            os.remove(path)
        else:
            if "__pycache__" == item:
                shutil.rmtree(path)
            tmp_path = os.path.join(path, "__pycache__")
            if os.path.exists(tmp_path):
                shutil.rmtree(tmp_path)

if __name__ == "__main__":
    main()
