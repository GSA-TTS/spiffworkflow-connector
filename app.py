import os

from spiffworkflow_proxy.blueprint import proxy_blueprint
from flask import Flask

app = Flask(__name__)
app.config.from_pyfile("config.py", silent=True)

if app.config.get("ENV", "development") != "production":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Use the SpiffConnector Blueprint, which will auto-discover any
# connector-* packages and provide API endpoints for listing and executing
# available services.
app.register_blueprint(proxy_blueprint)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    debug = os.environ.get("FLASK_ENV") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug)
