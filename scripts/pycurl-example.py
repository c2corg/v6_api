from urllib.parse import urlencode

import pycurl
from io import BytesIO

#curl -X PUT -H "Content-Type: application/json" -d @./scripts/esjson5-6/a.json http://192.168.1.120:9203/c2corg_a/_mapping/_doc

f = open("./scripts/esjson5-6/a.json")
post_data = f.read()

buffer = BytesIO()
c = pycurl.Curl()
c.setopt(c.URL, 'http://192.168.1.120:9203/c2corg_tests_a/_mapping/_doc')
header = ['Content-Type: application/json']
c.setopt(c.HTTPHEADER, header)
c.setopt(c.CUSTOMREQUEST, 'PUT')
# Form data must be provided already urlencoded.
# Sets request method to POST,
# Content-Type header to application/x-www-form-urlencoded
# and data to send in request body.
c.setopt(c.POSTFIELDS, post_data)
c.setopt(c.WRITEDATA, buffer)
c.perform()
c.close()

body = buffer.getvalue()
# Body is a byte string.
# We have to know the encoding in order to print it to a text file
# such as standard output.
print(body.decode('iso-8859-1'))
