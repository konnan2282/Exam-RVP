from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy.engine import Engine
from sqlalchemy import event

db = SQLAlchemy()

# Принудительное включение поддержки Foreign Keys для SQLite (чтобы работал ON DELETE CASCADE)
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

book_genre = db.Table('book_genre',
    db.Column('book_id', db.Integer, db.ForeignKey('books.id', ondelete='CASCADE'), primary_key=True),
    db.Column('genre_id', db.Integer, db.ForeignKey('genres.id', ondelete='CASCADE'), primary_key=True)
)

class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    middle_name = db.Column(db.String(50))
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    
    role = db.relationship('Role', backref='users')

    @property
    def get_fio(self):
        if self.middle_name:
            return f"{self.last_name} {self.first_name} {self.middle_name}"
        return f"{self.last_name} {self.first_name}"

    @property
    def is_admin(self):
        return self.role.name == 'Администратор'

    @property
    def is_moderator(self):
        return self.role.name == 'Модератор'

class Genre(db.Model):
    __tablename__ = 'genres'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

class Book(db.Model):
    __tablename__ = 'books'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    short_description = db.Column(db.Text, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    publisher = db.Column(db.String(255), nullable=False)
    author = db.Column(db.String(255), nullable=False)
    pages_count = db.Column(db.Integer, nullable=False)
    
    genres = db.relationship('Genre', secondary=book_genre, backref=db.backref('books', lazy=True))
    cover = db.relationship('Cover', backref='book', uselist=False, cascade="all, delete-orphan")
    reviews = db.relationship('Review', backref='book', cascade="all, delete-orphan")
    visits = db.relationship('VisitLog', backref='book', cascade="all, delete-orphan")

    @property
    def rating_info(self):
        ratings = [r.rating for r in self.reviews]
        if not ratings:
            return 0.0, 0
        avg_rating = sum(ratings) / len(ratings)
        return round(avg_rating, 2), len(ratings)

class Cover(db.Model):
    __tablename__ = 'covers'
    id = db.Column(db.Integer, primary_key=True)
    file_name = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    md5_hash = db.Column(db.String(255), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id', ondelete='CASCADE'), nullable=False)

class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    user = db.relationship('User')

class VisitLog(db.Model):
    __tablename__ = 'visit_logs'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    user = db.relationship('User')