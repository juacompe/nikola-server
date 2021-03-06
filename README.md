Prerequisites
----
Make sure you have `reddis-server` installed or you cannot start the scheduler and a worker.

To install `reddis-server` on Ubuntu, run the command below:

```
sudo apt-get install redis-server
```


To install all dependencies (I recommend a virtualenv):

```
pip install -r requirements.txt
```

Do usual Django-stuff, then edit conf.py and change `BASE_BLOG_PATH`,
`BASE_OUTPUT_PATH`, `URL_SUFFIX` (at least).

To start a worker:

```
python manage.py rqworker default
```

To start the test server:

```
python manage.py runserver
```

To start the scheduler (useful for post-dated posts):

```
rqscheduler
```

