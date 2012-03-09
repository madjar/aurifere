import os
from XyneXDG.BaseDirectory import get_data_home

DATA_DIR = os.path.join(get_data_home(), 'aurifere')
os.makedirs(DATA_DIR, exist_ok=True)
