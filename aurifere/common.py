import os
from XyneXDG.BaseDirectory import get_data_home

DATA_DIR = os.path.join(get_data_home(), 'aurifere')

if not os.path.isdir(DATA_DIR):
    os.mkdir(DATA_DIR)
