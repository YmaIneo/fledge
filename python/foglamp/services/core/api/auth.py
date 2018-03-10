# -*- coding: utf-8 -*-

# FOGLAMP_BEGIN
# See: http://foglamp.readthedocs.io/
# FOGLAMP_END

""" auth routes """

import re
from collections import OrderedDict

from aiohttp import web
from foglamp.services.core.user_model import User

__author__ = "Praveen Garg"
__copyright__ = "Copyright (c) 2017 OSIsoft, LLC"
__license__ = "Apache 2.0"
__version__ = "${VERSION}"


_help = """
    ------------------------------------------------------------------------------------
    | GET  POST PUT              | /foglamp/user                                       |
    | DELETE                     | /foglamp/user/{id}                                  |
    
    | POST                       | /foglamp/login                                      |
    | PUT                        | /foglamp/logout                                     |
    ------------------------------------------------------------------------------------
"""

# move to common  / config
JWT_SECRET = 'f0gl@mp'
JWT_ALGORITHM = 'HS256'
JWT_EXP_DELTA_SECONDS = 30*60  # 30 minutes


async def login(request):
    """ Validate user with its username and password

    :Example:
            curl -X POST -d '{"username": "user", "password": "User@123"}' http://localhost:8081/foglamp/login
    """

    data = await request.json()

    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        raise web.HTTPBadRequest(reason="Username or password is missing")

    try:
        token = User.Objects.login(username, password)
    except (User.DoesNotExist, User.PasswordDoesNotMatch) as ex:
        return web.HTTPBadRequest(reason=str(ex))
    except ValueError as exc:
        return web.HTTPBadRequest(reason=str(exc))

    return web.json_response({"message": "Logged in successfully", "token": token})


async def logout(request):
    """

    :param request:
    :return:

        curl -H "authorization: <token>" -X PUT http://localhost:8081/foglamp/logout

    """
    # invalidate token in DB
    return web.json_response({"logout": True})


async def get_roles(request):
    """ get roles

       :Example:
            curl -X GET http://localhost:8081/foglamp/user/role
    """
    result = User.Objects.roles()
    return web.json_response({'roles': result})


async def get_user(request):
    """ get user info

    :Example:
            curl -H "authorization: <token>" -X GET http://localhost:8081/foglamp/user
            curl -H "authorization: <token>" -X GET http://localhost:8081/foglamp/user?id=2
            curl -H "authorization: <token>" -X GET http://localhost:8081/foglamp/user?username=admin
            curl -H "authorization: <token>" -X GET "http://localhost:8081/foglamp/user?id=1&username=admin"
    """
    user_id = None
    user_name = None

    if 'id' in request.query:
        try:
            user_id = int(request.query['id'])
            if user_id <= 0:
                raise ValueError
        except ValueError:
            raise web.HTTPBadRequest(reason="Bad user id")

    if 'username' in request.query and request.query['username'] != '':
        user_name = request.query['username']

    if user_id or user_name:
        try:
            user = User.Objects.get(user_id, user_name)
            u = OrderedDict()
            u['userId'] = user.pop('id')
            u['userName'] = user.pop('uname')
            u['roleId'] = user.pop('role_id')
            result = u
        except User.DoesNotExist as ex:
            raise web.HTTPNotFound(reason=str(ex))
    else:
        users = User.Objects.all()
        res = []
        for row in users:
            u = OrderedDict()
            u["userId"] = row["id"]
            u["userName"] = row["uname"]
            u["roleId"] = row["role_id"]
            res.append(u)
        result = {'users': res}

    return web.json_response(result)


async def create_user(request):
    """ create user

    :Example:
        curl -X POST -d '{"username": "admin", "password": "F0gl@mp!"}' http://localhost:8081/foglamp/user
        curl -X POST -d '{"username": "ajadmin", "password": "User@123", "role": 1}' http://localhost:8081/foglamp/user
    """
    data = await request.json()

    username = data.get('username')
    password = data.get('password')

    # TODO: map 2 with normal user role id in db
    role_id = data.get('role', 2)
    role = int(role_id)

    if not username or not password:
        raise web.HTTPBadRequest(reason="Username or password is missing")

    # TODO:
    # 1) username regex? is email allowed?
    # 2) confirm password?
    if not re.match('((?=.*\d)(?=.*[A-Z])(?=.*\W).{6,}$)', password):
        raise web.HTTPBadRequest(reason="Password must contain at least one digit, "
                                        "one lowercase, one uppercase, "
                                        "one special character and "
                                        "length of minimum 6 characters")

    # TODO: Get role_id range from DB
    roles = [int(r["id"]) for r in User.Objects.roles]

    if role not in roles:
        raise web.HTTPBadRequest(reason="Bad Role Id")

    u = dict()
    try:
        result = User.Objects.create(username, password, role)
        # if user inserted then fetch user info
        if result['rows_affected']:
            # we should not do get again!
            # we just need uid, uname and role_id we have
            user = User.Objects.get(username=username)
            u['userId'] = user.pop('id')
            u['userName'] = user.pop('uname')
            u['roleId'] = user.pop('role_id')
    except ValueError as ex:
        raise web.HTTPBadRequest(reason=str(ex))
    except Exception as exc:
        raise web.HTTPInternalServerError(reason=str(exc))

    return web.json_response({'message': 'User has been created successfully', 'user': u})


async def update_user(request):
    pass


async def delete_user(request):
    """ Delete a user from users table

    :Example:
            curl -X DELETE  http://localhost:8081/foglamp/user/1
    """

    # TODO: soft delete?

    try:
        user_id = request.match_info.get('id')
        result = User.Objects.delete(user_id)

        if not result['rows_affected']:
            raise User.DoesNotExist

    except ValueError as ex:
        raise web.HTTPBadRequest(reason=str(ex))
    except User.DoesNotExist:
        raise web.HTTPBadRequest(reason="User does not exist")
    except Exception as exc:
        raise web.HTTPInternalServerError(reason=str(exc))

    return web.json_response({'message': "User has been deleted successfully"})
