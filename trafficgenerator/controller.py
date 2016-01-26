import flask 
app = flask.Flask(__name__)

@app.route("/newflowstarted", methods = ['POST'])
def hello():
    print flask.request.json
    return flask.jsonify(flask.request.json)

if __name__ == "__main__":
    app.run()
