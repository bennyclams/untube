from flask import Blueprint
from adless.api.v1 import v1

api = Blueprint("api", __name__)
api.register_blueprint(v1, url_prefix="/v1")