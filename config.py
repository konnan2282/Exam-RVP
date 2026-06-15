import os

class Config:
    SECRET_KEY = 'super-secret-key-change-it'
    
    # Использование SQLite вместо MySQL (создаст файл library.db в корне проекта)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(os.path.dirname(os.path.abspath(__file__)), 'library.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'covers')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024