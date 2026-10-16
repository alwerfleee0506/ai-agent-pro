import os
bind = '0.0.0.0:' + os.getenv('PORT','10000')
workers = 1
threads = 2
timeout = 180
accesslog = '-'
errorlog = '-'
