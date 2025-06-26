from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "OK", 200

def run_dummy_server():
    app.run(host="0.0.0.0", port=8000)
