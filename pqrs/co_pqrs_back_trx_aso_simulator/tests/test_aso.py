# import json
# import urllib.request
# import urllib.error

# data = json.dumps({
#     "card": {
#         "cardId": "4593170753249784"
#     }
# }).encode()

# req = urllib.request.Request(
#     "http://localhost:8050/cards/v2/operations",
#     data=data,
#     method="POST",
#     headers={
#         "Content-Type": "application/json"
#     },
# )

# try:
#     response = urllib.request.urlopen(req)

#     print("STATUS:", response.status)
#     print("HEADERS:", dict(response.headers))
#     print("BODY:", response.read().decode())

# except urllib.error.HTTPError as e:
#     print("STATUS:", e.code)
#     print("AUTHENTICATIONTYPE:", e.headers.get("authenticationtype"))
#     print("HEADERS:", dict(e.headers))
#     print("BODY:", e.read().decode())

import json
import urllib.request
import urllib.error


CARD_ID = "4593170753249784"
DEVICE_ID = "BB-04-CG0400002F3D"
PROFILE_ID = "CC000000003017449"


authentication_data = (
    f"deviceId={DEVICE_ID},"
    f"profileId={PROFILE_ID}"
)


data = json.dumps({
    "card": {
        "cardId": CARD_ID
    }
}).encode()


req = urllib.request.Request(
    "http://localhost:8050/cards/v2/operations",
    data=data,
    method="POST",
    headers={
        "Content-Type": "application/json",
        "authenticationtype": "241",
        "authenticationdata": authentication_data,
    },
)


try:
    response = urllib.request.urlopen(req)

    print("STATUS:", response.status)
    print("HEADERS:", dict(response.headers))
    print("BODY:", response.read().decode())

except urllib.error.HTTPError as e:
    print("STATUS:", e.code)
    print("AUTHENTICATIONTYPE:", e.headers.get("authenticationtype"))
    print("AUTHENTICATIONCHALLENGE:", e.headers.get("authenticationChallenge"))
    print("AUTHENTICATIONSTATE:", e.headers.get("authenticationstate"))
    print("HEADERS:", dict(e.headers))
    print("BODY:", e.read().decode())