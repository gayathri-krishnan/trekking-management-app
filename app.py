import os

from flask import Flask, render_template
from extensions import db

def create_app():
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY= os.environ.get('SECRET_KEY',"dev-key"),
        SQLALCHEMY_DATABASE_URI='sqlite:///trekking.db',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    #login_manager.init_app(app)

    @app.route('/')
    def home():
        return render_template('home.html')

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)