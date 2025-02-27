from flask import Flask

app = Flask(__name__)

@app.route("/")
def health_check():
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)  # Running on Port 8000 for Koyeb
